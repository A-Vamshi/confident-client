import asyncio
import logging
import threading
import weakref

from typing import Any, Callable, Dict, Optional

from ..prompts.types import Prompt as PromptPayload

logger = logging.getLogger(__name__)

MAX_BACKOFF = 8

_INTERVALS = "_refresh_intervals"

Refreshed = Callable[[str, str, PromptPayload], None]

_loop: Optional[asyncio.AbstractEventLoop] = None
_loop_lock = threading.Lock()


def _background_loop() -> asyncio.AbstractEventLoop:
    """The one event loop every prompt refreshes on.

    Started on first use rather than on import, so a program that never pulls
    a prompt never grows a thread.
    """
    global _loop

    with _loop_lock:
        if _loop is not None and _loop.is_running():
            return _loop

        ready = threading.Event()
        created: Dict[str, asyncio.AbstractEventLoop] = {}

        def run() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            created["loop"] = loop
            loop.call_soon(ready.set)
            loop.run_forever()

        threading.Thread(
            target=run, name="confidentai-prompt-refresh", daemon=True
        ).start()
        ready.wait()
        _loop = created["loop"]
        return _loop


def _intervals(prompt: Any) -> Dict[str, float]:
    """The selectors this handle is refreshing, and how often."""
    registry = getattr(prompt, _INTERVALS, None)
    if registry is None:
        registry = {}
        setattr(prompt, _INTERVALS, registry)
    return registry


def start_refresh(
    prompt: Any,
    key: str,
    selector: Dict[str, Optional[str]],
    *,
    every: float,
    on_refreshed: Refreshed,
) -> None:
    """Refresh `prompt` from `selector` every `every` seconds.

    Starting a refresh that is already running only retunes it: the running
    loop reads the interval each time round, so a later pull can change the
    rate without dropping a cycle or stacking a second loop on the selector.
    """
    registry = _intervals(prompt)
    running = key in registry
    registry[key] = every
    if running:
        return

    asyncio.run_coroutine_threadsafe(
        _refresh(weakref.ref(prompt), key, dict(selector), on_refreshed),
        _background_loop(),
    )


def stop_refresh(prompt: Any, key: str) -> None:
    """Stop refreshing one selector. The loop ends on its next wake-up."""
    _intervals(prompt).pop(key, None)


def stop_all_refresh(prompt: Any) -> None:
    """Stop refreshing every selector this handle pulled."""
    _intervals(prompt).clear()


async def _refresh(
    reference: "weakref.ref[Any]",
    key: str,
    selector: Dict[str, Optional[str]],
    on_refreshed: Refreshed,
) -> None:
    failures = 0
    while True:
        prompt = reference()
        if prompt is None:
            return
        interval = _intervals(prompt).get(key)
        if interval is None:
            return
        # Dropped before the sleep, so that waiting to refresh a prompt is
        # never what keeps it from being collected.
        del prompt

        await asyncio.sleep(interval * min(2**failures, MAX_BACKOFF))

        prompt = reference()
        if prompt is None:
            return
        if key not in _intervals(prompt):
            return

        try:
            payload = await prompt._a_pull_once(**selector)
            prompt_id = getattr(prompt, "prompt_id", None)
            if prompt_id is not None:
                on_refreshed(prompt_id, key, payload)
            failures = 0
        except Exception:
            failures += 1
            logger.warning(
                "could not refresh the prompt (%s); keeping the copy in "
                "hand and trying again later.",
                key,
                exc_info=True,
            )
        del prompt
