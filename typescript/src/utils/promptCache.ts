/**
 * The prompt cache, and the pull that reads and writes it.
 *
 * Pulling a prompt over the network on every use puts a round trip in front of
 * every LLM call, so a pulled prompt is kept on disk and refreshed in the
 * background. `pullPrompt` is what the generated `Prompt.pull` delegates to;
 * the refresh loop it starts lives in `promptRefresh`.
 *
 * Entries are keyed by prompt id and by the selector the caller pulled with,
 * so `latest` and the `production` label are separate entries and neither can
 * serve the other. The id is in the key because it is what the routes take,
 * which also means two projects using the same alias cannot collide here.
 */

import * as fs from "node:fs";
import * as path from "node:path";

import { Prompt as PromptPayload } from "../prompts/types";
import {
  PromptSelector,
  RefreshablePrompt,
  startRefresh,
  stopRefresh,
} from "./promptRefresh";

export const CACHE_DIRECTORY_VARIABLE = "CONFIDENT_CACHE_DIR";
export const DEFAULT_CACHE_DIRECTORY = ".confidentai";
export const CACHE_FILENAME = "prompts.json";

/** How a caller asked for the cache to behave on one pull. */
export interface CacheOptions {
  refresh?: number;
  fallbackToCache: boolean;
  writeToCache: boolean;
  defaultToCache: boolean;
}

type CacheFile = Record<string, Record<string, PromptPayload>>;

// One unwritable cache directory is reported once, not on every pull: a
// read-only filesystem is a deployment's steady state, not a passing fault.
let warnedUnwritable = false;

// ===== Where an entry lives =====

/**
 * The cache key for one way of selecting a commit.
 *
 * Derived in one place because the refresh loop and the pull that starts it
 * must agree on it: a loop that refreshes an entry nobody reads is invisible
 * until someone notices the prompt never changes.
 */
export function selectorKey(selector: PromptSelector): string {
  if (selector.label !== undefined) return `label:${selector.label}`;
  if (selector.version !== undefined) return `version:${selector.version}`;
  if (selector.commit === undefined && selector.branch !== undefined) {
    return `branch:${selector.branch}`;
  }
  return `commit:${selector.commit ?? "latest"}`;
}

/** The cache file, or undefined where the filesystem will not hold one. */
export function cacheFile(): string | undefined {
  const directory =
    process.env[CACHE_DIRECTORY_VARIABLE] || DEFAULT_CACHE_DIRECTORY;
  try {
    fs.mkdirSync(directory, { recursive: true });
  } catch (error) {
    if (!warnedUnwritable) {
      warnedUnwritable = true;
      console.warn(
        `Cannot write the prompt cache to ${directory} (${String(error)}); ` +
          `prompts will be pulled from the API every time. Set ` +
          `${CACHE_DIRECTORY_VARIABLE} to a writable directory to cache them.`,
      );
    }
    return undefined;
  }
  return path.join(directory, CACHE_FILENAME);
}

// ===== Reading and writing it =====

function readFile(): CacheFile {
  const file = cacheFile();
  if (file === undefined || !fs.existsSync(file)) return {};
  try {
    const contents: unknown = JSON.parse(fs.readFileSync(file, "utf8"));
    if (typeof contents !== "object" || contents === null) return {};
    return contents as CacheFile;
  } catch {
    // A half-written or hand-edited cache is not worth reporting: it is a
    // cache, and the pull that follows refills it.
    return {};
  }
}

/** The cached commit for one prompt and selector, if one is stored. */
export function readCached(
  promptId: string,
  key: string,
): PromptPayload | undefined {
  return readFile()[promptId]?.[key];
}

/**
 * Store one commit, replacing whatever that selector held before.
 *
 * The file is replaced rather than locked, so a reader always sees a whole
 * cache and two processes writing at once cost a refresh interval rather than
 * a corrupt file.
 */
export function writeCached(
  promptId: string,
  key: string,
  payload: PromptPayload,
): void {
  const file = cacheFile();
  if (file === undefined) return;

  const contents = readFile();
  contents[promptId] = { ...contents[promptId], [key]: payload };
  const staged = path.join(
    path.dirname(file),
    `${CACHE_FILENAME}.${process.pid}.${Date.now()}.tmp`,
  );
  try {
    fs.writeFileSync(staged, JSON.stringify(contents));
    fs.renameSync(staged, file);
  } catch (error) {
    console.warn(`Could not write the prompt cache: ${String(error)}`);
    try {
      fs.rmSync(staged, { force: true });
    } catch {
      // The staged file could not be written in the first place.
    }
  }
}

// ===== The pull the generated handle delegates to =====

function serveCached(
  prompt: RefreshablePrompt,
  promptId: string | undefined,
  key: string,
): boolean {
  if (promptId === undefined) return false;
  const cached = readCached(promptId, key);
  if (cached === undefined) return false;
  prompt.load(cached);
  return true;
}

/** Fill `prompt` from the cache or the API, per the caller's flags. */
export async function pullPrompt(
  prompt: RefreshablePrompt,
  selector: PromptSelector,
  options: CacheOptions,
): Promise<void> {
  const { refresh, fallbackToCache, defaultToCache } = options;
  const key = selectorKey(selector);
  const promptId = prompt.promptId;

  if (!refresh) {
    // No refresh means no cache at all: every pull calls the API, which is
    // what you want while you are editing the prompt.
    stopRefresh(prompt, key);
    await prompt.pullOnce(selector);
    return;
  }

  let writeToCache = false;
  if (promptId !== undefined) {
    startRefresh(prompt, key, selector, refresh, writeCached);
    // The refresh loop owns the cache from here; the pull that started it
    // writes only the entry that was missing, so that the next cold start has
    // something to fall back to.
    writeToCache =
      options.writeToCache && readCached(promptId, key) === undefined;
  }
  if (defaultToCache && serveCached(prompt, promptId, key)) return;

  let payload: PromptPayload;
  try {
    payload = await prompt.pullOnce(selector);
  } catch (error) {
    if (fallbackToCache && serveCached(prompt, promptId, key)) {
      console.warn(
        "Could not pull the prompt; serving the cached copy.",
        error,
      );
      return;
    }
    throw error;
  }

  if (writeToCache && promptId !== undefined) {
    writeCached(promptId, key, payload);
  }
}
