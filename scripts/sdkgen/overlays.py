"""Hand-written code folded into generated files, after rendering.

The generator says what the spec says. A few things a client needs are not in
the spec at all and belong on a generated class anyway — prompt caching and
background refresh is the first of them. An overlay states one such edit
against one rendered file.

Overlays are applied to the rendered text before anything is written, so
`--check`, the idempotence guarantee and both formatters cover overlaid code
exactly as they cover generated code. Every anchor must match the number of
times it says: a generator change that moves one fails the run rather than
quietly dropping the feature.

Prefer leaving logic here as thin as it will go. An overlay is best at
renaming a generated method out of the way and calling it from a hand-written
one; the hand-written one belongs in the SDK, where it is read, typed and
tested like the rest of the library.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple

from .constants import REPO_ROOT
from .core.errors import SpecError
from .core.output import format_python, format_typescript


@dataclass(frozen=True)
class Edit:
    """One exact replacement, and how many times it must match."""

    anchor: str
    replacement: str
    occurrences: int = 1


@dataclass(frozen=True)
class Overlay:
    """The edits one generated file takes after it is rendered."""

    path: str
    edits: Tuple[Edit, ...] = field(default_factory=tuple)

    def apply(self, text: str) -> str:
        for edit in self.edits:
            found = text.count(edit.anchor)
            if found != edit.occurrences:
                raise SpecError(
                    f"the overlay for {self.path} expected "
                    f"{edit.occurrences} occurrence(s) of\n\n"
                    f"{edit.anchor}\n\n"
                    f"but the generated file has {found}. The generator's "
                    "output moved; update the overlay in "
                    "sdkgen/overlays.py to match it."
                )
            text = text.replace(edit.anchor, edit.replacement)
        return text


# ===== Prompts: caching and background refresh =====

# `pull` is generated from three routes the caller chooses between, and that
# dispatch is worth keeping generated. So the generated method becomes the
# private one-shot fetch, returning the payload it already loaded, and the
# `pull` a caller sees is written here on top of it — which is also why a
# refresh can re-pull without a second copy of the dispatch to keep in step.

_PULL_DOCSTRING = '''        """Pull the prompt into this handle, and keep it current.

        Pass at most one of commit, version, label. The commit that comes back
        is cached on disk and re-pulled in the background every `refresh`
        seconds, so editing the prompt on Confident AI reaches a running
        process without a deploy.

        Args:
            commit: The hash of the commit to pull. Defaults to `latest`.
            version: The version number of the prompt to pull.
            label: The label of the version to pull.
            branch: The name of the branch to read from. Defaults to `main`
                when omitted. Only valid with `commit`.
            refresh: How often, in seconds, to re-pull the prompt in the
                background. `0` turns off the refresh and the cache together,
                so that every pull calls the API — which is what you want
                while you are still editing the prompt.
            fallback_to_cache: Serve the cached commit when the API cannot be
                reached, instead of raising.
            write_to_cache: Write the pulled commit to the cache. The
                background refresh writes it either way.
            default_to_cache: Return the cached commit when there is one,
                rather than waiting for the API.
        """
'''

_PULL_PARAMETERS = """        self,
        *,
        commit: Optional[str] = None,
        version: Optional[str] = None,
        label: Optional[str] = None,
        branch: Optional[str] = None,
        refresh: Optional[int] = 60,
        fallback_to_cache: bool = True,
        write_to_cache: bool = True,
        default_to_cache: bool = True,
    ) -> "Prompt":
"""

_PULL_BODY = """        {prefix}{call}(
            self,
            {{
                "commit": commit,
                "version": version,
                "label": label,
                "branch": branch,
            }},
            refresh=refresh,
            fallback_to_cache=fallback_to_cache,
            write_to_cache=write_to_cache,
            default_to_cache=default_to_cache,
        )
"""

_TS_PULL_DOC = """  /**
   * Pull the prompt into this handle, and keep it current.
   *
   * Pass at most one of commit, version, label. The commit that comes back is
   * cached on disk and re-pulled in the background every `refresh` seconds, so
   * editing the prompt on Confident AI reaches a running process without a
   * deploy.
   *
   * @param options.commit The hash of the commit to pull. Defaults to
   *   `latest`.
   * @param options.version The version number of the prompt to pull.
   * @param options.label The label of the version to pull.
   * @param options.branch The name of the branch to read from. Defaults to
   *   `main` when omitted. Only valid with `commit`.
   * @param options.refresh How often, in seconds, to re-pull the prompt in the
   *   background. `0` turns off the refresh and the cache together, so that
   *   every pull calls the API — which is what you want while you are still
   *   editing the prompt.
   * @param options.fallbackToCache Serve the cached commit when the API cannot
   *   be reached, instead of throwing.
   * @param options.writeToCache Write the pulled commit to the cache. The
   *   background refresh writes it either way.
   * @param options.defaultToCache Return the cached commit when there is one,
   *   rather than waiting for the API.
   */
"""

_TS_PULL = """  async pull(
    options: {
      commit?: string;
      version?: string;
      label?: string;
      branch?: string;
      refresh?: number;
      fallbackToCache?: boolean;
      writeToCache?: boolean;
      defaultToCache?: boolean;
    } = {},
  ): Promise<this> {
    const {
      refresh = 60,
      fallbackToCache = true,
      writeToCache = true,
      defaultToCache = true,
      ...selector
    } = options;
    await pullPrompt(this, selector, {
      refresh,
      fallbackToCache,
      writeToCache,
      defaultToCache,
    });
    return this;
  }

"""


def _python_pull(descriptive: bool) -> str:
    """The `pull` pair a caller sees, wrapping the generated one-shot fetch."""
    docstring = _PULL_DOCSTRING if descriptive else ""
    sync = _PULL_BODY.format(prefix="return ", call="pull_prompt")
    waited = _PULL_BODY.format(prefix="return await ", call="a_pull_prompt")
    return (
        "    def pull(\n"
        + _PULL_PARAMETERS
        + docstring
        + sync
        + "\n"
        + "    async def a_pull(\n"
        + _PULL_PARAMETERS
        + docstring
        + waited
        + "\n"
    )


def prompts_overlay(descriptive: bool) -> Overlay:
    return Overlay(
        path="python/confidentai/prompts/prompt.py",
        edits=(
            Edit(
                "from confidentai.utils.helpers import interpolate_prompt",
                "from confidentai.utils.helpers import interpolate_prompt\n"
                "from confidentai.utils.prompt_cache import (\n"
                "    a_pull_prompt,\n"
                "    pull_prompt,\n"
                ")",
            ),
            Edit("    def pull(\n", "    def _pull_once(\n"),
            Edit("    async def a_pull(\n", "    async def _a_pull_once(\n"),
            Edit('    ) -> "Prompt":\n', "    ) -> PromptPayload:\n", 2),
            Edit(
                "        self._load(payload)\n        return self\n",
                "        self._load(payload)\n        return payload\n",
                2,
            ),
            Edit(
                "    def _prompt_id(self) -> str:\n",
                _python_pull(descriptive)
                + "    def _prompt_id(self) -> str:\n",
            ),
        ),
    )


def ts_prompts_overlay(descriptive: bool) -> Overlay:
    return Overlay(
        path="typescript/src/prompts/prompt.ts",
        edits=(
            Edit(
                'import { interpolatePrompt } from "../utils/helpers";',
                'import { interpolatePrompt } from "../utils/helpers";\n'
                'import { pullPrompt } from "../utils/promptCache";',
            ),
            Edit("  async pull(\n", "  /** @internal */\n  async pullOnce(\n"),
            Edit("  ): Promise<this> {\n", "  ): Promise<PromptPayload> {\n"),
            Edit(
                "    this.load(payload);\n    return this;\n",
                "    this.load(payload);\n    return payload;\n",
            ),
            Edit(
                "  private load(payload: PromptPayload): void {\n",
                "  /** @internal */\n"
                "  load(payload: PromptPayload): void {\n",
            ),
            Edit(
                "  private promptIdOrThrow(): string {\n",
                (_TS_PULL_DOC if descriptive else "")
                + _TS_PULL
                + "  private promptIdOrThrow(): string {\n",
            ),
        ),
    )


def overlays(descriptive: bool) -> List[Overlay]:
    return [prompts_overlay(descriptive), ts_prompts_overlay(descriptive)]


# ===== Applying them =====


def run_after_generation(
    outputs: List[Tuple[Path, str]], descriptive: bool = True
) -> List[Tuple[Path, str]]:
    """Fold every overlay into the files it names, before any are written."""
    pending: Dict[str, Overlay] = {
        overlay.path: overlay for overlay in overlays(descriptive)
    }

    applied: List[Tuple[Path, str]] = []
    for path, content in outputs:
        overlay = pending.pop(str(path.relative_to(REPO_ROOT)), None)
        if overlay is None:
            applied.append((path, content))
            continue
        name = str(path.relative_to(REPO_ROOT))
        overlaid = overlay.apply(content)
        # Both formatters have already run, so an overlaid file goes back
        # through its own to land on the same house style as everything else.
        if path.suffix == ".py":
            overlaid = format_python(overlaid)
        else:
            overlaid = format_typescript({name: overlaid})[name]
        applied.append((path, overlaid))

    if pending:
        raise SpecError(
            "these overlays name a file the generator does not produce: "
            + ", ".join(sorted(pending))
            + ". Update sdkgen/overlays.py, or the resource it overlays."
        )
    return applied
