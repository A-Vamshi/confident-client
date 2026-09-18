"""The prompts overlay: caching and background refresh on `pull`.

`pull` is generated from three routes the caller chooses between, and that
dispatch is worth keeping generated. So the generated method becomes the
private one-shot fetch, returning the payload it already loaded, and the
`pull` a caller sees is written on top of it — which is also why a refresh can
re-pull without a second copy of the dispatch to keep in step.

The code these edits call lives in the SDK, in `confidentai/utils/`, where it
is typed and tested like the rest of the library.
"""

import re
from .overlay import Edit, Overlay


# ===== Prompts: caching and background refresh =====

_PULL = '''\
    def pull(
        self,
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
        """Pull the prompt into this handle, and keep it current.

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
        return pull_prompt(
            self,
            {
                "commit": commit,
                "version": version,
                "label": label,
                "branch": branch,
            },
            refresh=refresh,
            fallback_to_cache=fallback_to_cache,
            write_to_cache=write_to_cache,
            default_to_cache=default_to_cache,
        )

    async def a_pull(
        self,
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
        """Pull the prompt into this handle, and keep it current.

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
        return await a_pull_prompt(
            self,
            {
                "commit": commit,
                "version": version,
                "label": label,
                "branch": branch,
            },
            refresh=refresh,
            fallback_to_cache=fallback_to_cache,
            write_to_cache=write_to_cache,
            default_to_cache=default_to_cache,
        )

'''

# A docstring is one `"""` block at method-body indent, which `--descriptive
# false` drops along with every generated one.
_DOCSTRING = re.compile(r'\n        """.*?"""\n', re.S)


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
    return _PULL if descriptive else _DOCSTRING.sub("\n", _PULL)


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
