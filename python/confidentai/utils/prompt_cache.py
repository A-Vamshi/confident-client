"""The prompt cache, and the pull that reads and writes it.

Pulling a prompt over the network on every use puts a round trip in front of
every LLM call, so a pulled prompt is kept on disk and refreshed in the
background. `pull_prompt` is what the generated `Prompt.pull` delegates to;
the refresh loop it starts lives in `prompt_refresh`.

Entries are keyed by prompt id and by the selector the caller pulled with, so
`latest` and the `production` label are separate entries and neither can serve
the other. The id is in the key because it is what the routes take, which also
means two projects using the same alias cannot collide here.
"""

import json
import logging
import os
import tempfile

from pathlib import Path
from typing import Any, Dict, Optional, TypeVar

from pydantic import TypeAdapter

from ..prompts.types import Prompt as PromptPayload
from .prompt_refresh import start_refresh, stop_refresh

logger = logging.getLogger(__name__)

CACHE_DIRECTORY_VARIABLE = "CONFIDENT_CACHE_DIR"
DEFAULT_CACHE_DIRECTORY = ".confidentai"
CACHE_FILENAME = "prompts.json"

_PAYLOAD = TypeAdapter(PromptPayload)

# One unwritable cache directory is reported once, not on every pull: a
# read-only filesystem is a deployment's steady state, not a passing fault.
_warned_unwritable = False

Handle = TypeVar("Handle")


# ===== Where an entry lives =====


def selector_key(
    *,
    commit: Optional[str] = None,
    version: Optional[str] = None,
    label: Optional[str] = None,
    branch: Optional[str] = None,
) -> str:
    """The cache key for one way of selecting a commit.

    Derived in one place because the refresh loop and the pull that starts it
    must agree on it: a loop that refreshes an entry nobody reads is invisible
    until someone notices the prompt never changes.
    """
    if label is not None:
        return f"label:{label}"
    if version is not None:
        return f"version:{version}"
    if commit is None and branch is not None:
        return f"branch:{branch}"
    return f"commit:{commit or 'latest'}"


def cache_file() -> Optional[Path]:
    """The cache file, or None where the filesystem will not hold one."""
    global _warned_unwritable

    directory = Path(
        os.environ.get(CACHE_DIRECTORY_VARIABLE) or DEFAULT_CACHE_DIRECTORY
    )
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        if not _warned_unwritable:
            _warned_unwritable = True
            logger.warning(
                "cannot write the prompt cache to %s (%s); prompts will be "
                "pulled from the API every time. Set %s to a writable "
                "directory to cache them.",
                directory,
                error,
                CACHE_DIRECTORY_VARIABLE,
            )
        return None
    return directory / CACHE_FILENAME


# ===== Reading and writing it =====


def _read_file() -> Dict[str, Any]:
    path = cache_file()
    if path is None or not path.exists():
        return {}
    try:
        contents = json.loads(path.read_text())
    except (OSError, ValueError):
        # A half-written or hand-edited cache is not worth reporting: it is a
        # cache, and the pull that follows refills it.
        return {}
    return contents if isinstance(contents, dict) else {}


def read_cached(prompt_id: str, key: str) -> Optional[PromptPayload]:
    """The cached commit for one prompt and selector, if one is stored."""
    entry = _read_file().get(prompt_id, {}).get(key)
    if not isinstance(entry, dict):
        return None
    try:
        return _PAYLOAD.validate_python(entry)
    except ValueError:
        # Written by an older SDK against a since-changed shape.
        return None


def write_cached(prompt_id: str, key: str, payload: PromptPayload) -> None:
    """Store one commit, replacing whatever that selector held before.

    The file is replaced rather than locked, so a reader always sees a whole
    cache and two processes writing at once cost a refresh interval rather
    than a corrupt file.
    """
    path = cache_file()
    if path is None:
        return

    contents = _read_file()
    contents.setdefault(prompt_id, {})[key] = payload.model_dump(
        by_alias=True, mode="json"
    )
    try:
        with tempfile.NamedTemporaryFile(
            "w", dir=path.parent, prefix=path.name, suffix=".tmp", delete=False
        ) as handle:
            json.dump(contents, handle)
            staged = Path(handle.name)
        os.replace(staged, path)
    except OSError as error:
        logger.warning("could not write the prompt cache: %s", error)


# ===== The pull the generated handle delegates to =====


def _serve_cached(prompt: Any, prompt_id: Optional[str], key: str) -> bool:
    """Load the cached commit onto the handle, if there is one to load."""
    if prompt_id is None:
        return False
    cached = read_cached(prompt_id, key)
    if cached is None:
        return False
    prompt._load(cached)
    return True


def _has_entry(prompt_id: str, key: str) -> bool:
    return key in _read_file().get(prompt_id, {})


def _open(
    prompt: Any,
    selector: Dict[str, Optional[str]],
    key: str,
    prompt_id: Optional[str],
    refresh: Optional[int],
    write_to_cache: bool,
) -> bool:
    """Start refreshing this selector, and say whether the pull still writes.

    The refresh loop owns the cache once it is running, so the pull that
    started it writes only the entry that was missing — enough that the next
    cold start has something to fall back to.
    """
    if prompt_id is None:
        return False
    start_refresh(
        prompt, key, selector, every=refresh, on_refreshed=write_cached
    )
    return write_to_cache and not _has_entry(prompt_id, key)


def pull_prompt(
    prompt: Handle,
    selector: Dict[str, Optional[str]],
    *,
    refresh: Optional[int],
    fallback_to_cache: bool,
    write_to_cache: bool,
    default_to_cache: bool,
) -> Handle:
    """Fill `prompt` from the cache or the API, per the caller's flags."""
    key = selector_key(**selector)
    prompt_id = getattr(prompt, "prompt_id", None)

    if not refresh:
        # No refresh means no cache at all: every pull calls the API, which is
        # what you want while you are editing the prompt.
        stop_refresh(prompt, key)
        prompt._pull_once(**selector)
        return prompt

    write_to_cache = _open(
        prompt, selector, key, prompt_id, refresh, write_to_cache
    )
    if default_to_cache and _serve_cached(prompt, prompt_id, key):
        return prompt

    try:
        payload = prompt._pull_once(**selector)
    except Exception:
        if fallback_to_cache and _serve_cached(prompt, prompt_id, key):
            logger.warning(
                "could not pull the prompt; serving the cached copy.",
                exc_info=True,
            )
            return prompt
        raise

    if write_to_cache and prompt_id is not None:
        write_cached(prompt_id, key, payload)
    return prompt


async def a_pull_prompt(
    prompt: Handle,
    selector: Dict[str, Optional[str]],
    *,
    refresh: Optional[int],
    fallback_to_cache: bool,
    write_to_cache: bool,
    default_to_cache: bool,
) -> Handle:
    """`pull_prompt`, awaiting the API instead of blocking on it."""
    key = selector_key(**selector)
    prompt_id = getattr(prompt, "prompt_id", None)

    if not refresh:
        stop_refresh(prompt, key)
        await prompt._a_pull_once(**selector)
        return prompt

    write_to_cache = _open(
        prompt, selector, key, prompt_id, refresh, write_to_cache
    )
    if default_to_cache and _serve_cached(prompt, prompt_id, key):
        return prompt

    try:
        payload = await prompt._a_pull_once(**selector)
    except Exception:
        if fallback_to_cache and _serve_cached(prompt, prompt_id, key):
            logger.warning(
                "could not pull the prompt; serving the cached copy.",
                exc_info=True,
            )
            return prompt
        raise

    if write_to_cache and prompt_id is not None:
        write_cached(prompt_id, key, payload)
    return prompt
