"""The prompt cache, and the background refresh that keeps it warm.

Every test points ``CONFIDENT_CACHE_DIR`` at a tmp_path, so nothing here can
read or write the cache of the machine it runs on.
"""

import asyncio
import json

import pytest

from confidentai.prompts.types import TextPrompt
from confidentai.utils import prompt_cache, prompt_refresh
from confidentai.utils.prompt_cache import (
    CACHE_DIRECTORY_VARIABLE,
    CACHE_FILENAME,
    a_pull_prompt,
    pull_prompt,
    read_cached,
    selector_key,
    write_cached,
)


@pytest.fixture(autouse=True)
def cache_directory(tmp_path, monkeypatch):
    monkeypatch.setenv(CACHE_DIRECTORY_VARIABLE, str(tmp_path))
    return tmp_path


def a_prompt(text: str = "Hello {name}") -> TextPrompt:
    return TextPrompt(
        id="<PROMPT-ID>",
        alias="greeting",
        hash="bab04ce",
        type="TEXT",
        interpolationType="FSTRING",
        outputType="TEXT",
        text=text,
    )


class FakeHandle:
    """A prompt handle with the two members the cache reaches for."""

    def __init__(self, payload=None, fails: bool = False) -> None:
        self.prompt_id = "<PROMPT-ID>"
        self.loaded = None
        self.pulls = 0
        self._payload = payload if payload is not None else a_prompt()
        self._fails = fails

    def _pull_once(self, **selector):
        self.pulls += 1
        if self._fails:
            raise RuntimeError("the API is unreachable")
        self._load(self._payload)
        return self._payload

    async def _a_pull_once(self, **selector):
        return self._pull_once(**selector)

    def _load(self, payload) -> None:
        self.loaded = payload


def pull(handle, **overrides):
    options = {
        "refresh": 60,
        "fallback_to_cache": True,
        "write_to_cache": True,
        "default_to_cache": True,
    }
    options.update(overrides)
    selector = {
        name: options.pop(name, None)
        for name in ("commit", "version", "label", "branch")
    }
    return pull_prompt(handle, selector, **options)


# ===== The key an entry is filed under =====


def test_selector_key_distinguishes_every_way_of_selecting_a_commit():
    keys = {
        selector_key(),
        selector_key(commit="bab04ce"),
        selector_key(version="00.00.01"),
        selector_key(label="production"),
        selector_key(branch="dev"),
    }
    assert len(keys) == 5


def test_no_selector_is_the_latest_commit():
    assert selector_key() == selector_key(commit="latest")


def test_a_branch_only_pull_has_its_own_key():
    # The refresh loop and the pull that starts it derive the key the same
    # way, so a branch-only pull refreshes the entry it actually reads.
    assert selector_key(branch="dev") != selector_key()


def test_a_branch_narrows_a_commit_rather_than_replacing_it():
    assert selector_key(commit="bab04ce", branch="dev") == selector_key(
        commit="bab04ce"
    )


# ===== Reading and writing the file =====


def test_a_written_entry_reads_back(cache_directory):
    write_cached("<PROMPT-ID>", "commit:latest", a_prompt())
    assert read_cached("<PROMPT-ID>", "commit:latest").text == "Hello {name}"
    assert (cache_directory / CACHE_FILENAME).exists()


def test_entries_are_kept_apart_by_prompt_and_by_selector():
    write_cached("<PROMPT-ID>", "commit:latest", a_prompt("first"))
    write_cached("<PROMPT-ID>", "label:production", a_prompt("second"))
    write_cached("<OTHER-ID>", "commit:latest", a_prompt("third"))

    assert read_cached("<PROMPT-ID>", "commit:latest").text == "first"
    assert read_cached("<PROMPT-ID>", "label:production").text == "second"
    assert read_cached("<OTHER-ID>", "commit:latest").text == "third"


def test_a_missing_entry_is_not_an_error():
    assert read_cached("<PROMPT-ID>", "commit:latest") is None


def test_a_corrupt_cache_is_treated_as_empty(cache_directory):
    (cache_directory / CACHE_FILENAME).write_text("{not json")
    assert read_cached("<PROMPT-ID>", "commit:latest") is None


def test_an_entry_written_against_an_older_shape_is_ignored(cache_directory):
    (cache_directory / CACHE_FILENAME).write_text(
        json.dumps({"<PROMPT-ID>": {"commit:latest": {"gone": "fishing"}}})
    )
    assert read_cached("<PROMPT-ID>", "commit:latest") is None


def test_an_unwritable_cache_directory_does_not_raise(monkeypatch, tmp_path):
    unwritable = tmp_path / "file-not-a-directory"
    unwritable.write_text("")
    monkeypatch.setenv(CACHE_DIRECTORY_VARIABLE, str(unwritable / "cache"))
    monkeypatch.setattr(prompt_cache, "_warned_unwritable", False)

    write_cached("<PROMPT-ID>", "commit:latest", a_prompt())
    assert read_cached("<PROMPT-ID>", "commit:latest") is None


# ===== What one pull does =====


def test_the_first_pull_calls_the_api_and_seeds_the_cache():
    handle = FakeHandle()
    pull(handle)

    assert handle.pulls == 1
    assert handle.loaded is not None
    assert read_cached("<PROMPT-ID>", "commit:latest") is not None


def test_a_later_pull_is_served_from_the_cache():
    pull(FakeHandle())
    second = FakeHandle()
    pull(second)

    assert second.pulls == 0
    assert second.loaded.text == "Hello {name}"


def test_default_to_cache_off_always_calls_the_api():
    pull(FakeHandle())
    second = FakeHandle()
    pull(second, default_to_cache=False)

    assert second.pulls == 1


def test_refresh_zero_neither_reads_nor_writes_the_cache(cache_directory):
    handle = FakeHandle()
    pull(handle, refresh=0)

    assert handle.pulls == 1
    assert not (cache_directory / CACHE_FILENAME).exists()


def test_refresh_zero_calls_the_api_even_with_an_entry_cached():
    pull(FakeHandle())
    second = FakeHandle()
    pull(second, refresh=0)

    assert second.pulls == 1


def test_write_to_cache_off_leaves_the_cache_alone(cache_directory):
    pull(FakeHandle(), write_to_cache=False)
    assert not (cache_directory / CACHE_FILENAME).exists()


def test_a_cached_copy_is_served_when_the_api_cannot_be_reached():
    pull(FakeHandle())
    offline = FakeHandle(fails=True)
    pull(offline, default_to_cache=False)

    assert offline.loaded.text == "Hello {name}"


def test_an_unreachable_api_raises_when_nothing_is_cached():
    with pytest.raises(RuntimeError):
        pull(FakeHandle(fails=True))


def test_an_unreachable_api_raises_when_the_fallback_is_off():
    pull(FakeHandle())
    with pytest.raises(RuntimeError):
        pull(
            FakeHandle(fails=True),
            default_to_cache=False,
            fallback_to_cache=False,
        )


def test_the_async_pull_behaves_like_the_sync_one():
    handle = FakeHandle()
    asyncio.run(
        a_pull_prompt(
            handle,
            {"commit": None, "version": None, "label": None, "branch": None},
            refresh=60,
            fallback_to_cache=True,
            write_to_cache=True,
            default_to_cache=True,
        )
    )
    assert handle.pulls == 1
    assert read_cached("<PROMPT-ID>", "commit:latest") is not None


# ===== Starting and stopping the refresh =====


def test_a_pull_that_refreshes_registers_the_selector_it_pulled():
    handle = FakeHandle()
    pull(handle, label="production")
    assert set(prompt_refresh._intervals(handle)) == {"label:production"}


def test_refresh_zero_registers_nothing():
    handle = FakeHandle()
    pull(handle, refresh=0)
    assert prompt_refresh._intervals(handle) == {}


def test_pulling_again_retunes_the_interval_rather_than_stacking_a_loop():
    handle = FakeHandle()
    pull(handle)
    pull(handle, refresh=5)

    intervals = prompt_refresh._intervals(handle)
    assert intervals == {"commit:latest": 5}


def test_a_later_pull_with_refresh_off_stops_the_refresh():
    handle = FakeHandle()
    pull(handle)
    pull(handle, refresh=0)

    assert prompt_refresh._intervals(handle) == {}


def test_two_selectors_refresh_independently():
    handle = FakeHandle()
    pull(handle, label="production")
    pull(handle, version="00.00.01")

    assert set(prompt_refresh._intervals(handle)) == {
        "label:production",
        "version:00.00.01",
    }


def test_a_refresh_that_fails_never_reaches_the_caller():
    handle = FakeHandle(fails=True)
    reference = prompt_refresh.weakref.ref(handle)
    prompt_refresh._intervals(handle)["commit:latest"] = 0.001

    async def once():
        task = asyncio.ensure_future(
            prompt_refresh._refresh(
                reference, "commit:latest", {}, lambda *args: None
            )
        )
        await asyncio.sleep(0.05)
        prompt_refresh.stop_refresh(handle, "commit:latest")
        await asyncio.sleep(0.05)
        task.cancel()

    asyncio.run(once())
    assert handle.pulls >= 1


# ===== What the overlay leaves on the generated handle =====


def test_the_generated_handle_pulls_through_the_cache():
    import inspect

    from confidentai.prompts.prompt import Prompt

    parameters = inspect.signature(Prompt.pull).parameters
    assert "refresh" in parameters
    assert parameters["refresh"].default == 60
    for name in ("fallback_to_cache", "write_to_cache", "default_to_cache"):
        assert parameters[name].default is True

    # The spec-derived dispatch stays generated, one layer down, so a refresh
    # re-pulls through the same code a caller does.
    assert callable(Prompt._pull_once)
    assert inspect.iscoroutinefunction(Prompt._a_pull_once)


def test_the_refresh_loop_can_reach_what_it_needs_of_a_real_handle():
    from confidentai.api import Api
    from confidentai.prompts.prompt import Prompt

    handle = Prompt(
        Api(api_key="confident_us_proj_test"), prompt_id="<PROMPT-ID>"
    )
    # The loop reads the id off the handle, re-pulls, and loads the result.
    # These are the three names it knows; the overlay is what puts them there.
    assert handle.prompt_id == "<PROMPT-ID>"
    assert callable(handle._a_pull_once)
    assert callable(handle._load)
    assert prompt_refresh._intervals(handle) == {}
