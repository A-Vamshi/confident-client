/**
 * The prompt cache, and the background refresh that keeps it warm.
 *
 * Every test points `CONFIDENT_CACHE_DIR` at a fresh temporary directory, so
 * nothing here can read or write the cache of the machine it runs on.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

import { Prompt as PromptPayload } from "../src/prompts/types";
import {
  CACHE_DIRECTORY_VARIABLE,
  CACHE_FILENAME,
  pullPrompt,
  readCached,
  selectorKey,
  writeCached,
} from "../src/utils/promptCache";
import {
  PromptSelector,
  RefreshablePrompt,
  stopAllRefresh,
} from "../src/utils/promptRefresh";

const aPrompt = (text = "Hello {name}"): PromptPayload =>
  ({
    id: "<PROMPT-ID>",
    alias: "greeting",
    hash: "bab04ce",
    type: "TEXT",
    interpolationType: "FSTRING",
    outputType: "TEXT",
    text,
  }) as unknown as PromptPayload;

class FakeHandle implements RefreshablePrompt {
  promptId? = "<PROMPT-ID>";
  loaded?: PromptPayload;
  pulls = 0;

  constructor(
    private readonly payload: PromptPayload = aPrompt(),
    private readonly fails = false,
  ) {}

  async pullOnce(): Promise<PromptPayload> {
    this.pulls += 1;
    if (this.fails) throw new Error("the API is unreachable");
    this.load(this.payload);
    return this.payload;
  }

  load(payload: PromptPayload): void {
    this.loaded = payload;
  }
}

const pull = (
  handle: RefreshablePrompt,
  overrides: Partial<{
    refresh: number;
    fallbackToCache: boolean;
    writeToCache: boolean;
    defaultToCache: boolean;
  }> & { selector?: PromptSelector } = {},
) => {
  const { selector = {}, ...options } = overrides;
  return pullPrompt(handle, selector, {
    refresh: 60,
    fallbackToCache: true,
    writeToCache: true,
    defaultToCache: true,
    ...options,
  });
};

describe("the prompt cache", () => {
  const ORIGINAL_ENV = { ...process.env };
  let directory: string;

  beforeEach(() => {
    directory = fs.mkdtempSync(path.join(os.tmpdir(), "confident-cache-"));
    process.env[CACHE_DIRECTORY_VARIABLE] = directory;
  });

  afterEach(() => {
    fs.rmSync(directory, { recursive: true, force: true });
    process.env = { ...ORIGINAL_ENV };
  });

  // ===== The key an entry is filed under =====

  it("distinguishes every way of selecting a commit", () => {
    const keys = new Set([
      selectorKey({}),
      selectorKey({ commit: "bab04ce" }),
      selectorKey({ version: "00.00.01" }),
      selectorKey({ label: "production" }),
      selectorKey({ branch: "dev" }),
    ]);
    expect(keys.size).toBe(5);
  });

  it("treats no selector as the latest commit", () => {
    expect(selectorKey({})).toBe(selectorKey({ commit: "latest" }));
  });

  it("gives a branch-only pull its own key", () => {
    // The refresh loop and the pull that starts it derive the key the same
    // way, so a branch-only pull refreshes the entry it actually reads.
    expect(selectorKey({ branch: "dev" })).not.toBe(selectorKey({}));
  });

  it("lets a branch narrow a commit rather than replace it", () => {
    expect(selectorKey({ commit: "bab04ce", branch: "dev" })).toBe(
      selectorKey({ commit: "bab04ce" }),
    );
  });

  // ===== Reading and writing the file =====

  it("reads back what it wrote", () => {
    writeCached("<PROMPT-ID>", "commit:latest", aPrompt());
    expect(readCached("<PROMPT-ID>", "commit:latest")).toMatchObject({
      text: "Hello {name}",
    });
    expect(fs.existsSync(path.join(directory, CACHE_FILENAME))).toBe(true);
  });

  it("keeps entries apart by prompt and by selector", () => {
    writeCached("<PROMPT-ID>", "commit:latest", aPrompt("first"));
    writeCached("<PROMPT-ID>", "label:production", aPrompt("second"));
    writeCached("<OTHER-ID>", "commit:latest", aPrompt("third"));

    expect(readCached("<PROMPT-ID>", "commit:latest")).toMatchObject({
      text: "first",
    });
    expect(readCached("<PROMPT-ID>", "label:production")).toMatchObject({
      text: "second",
    });
    expect(readCached("<OTHER-ID>", "commit:latest")).toMatchObject({
      text: "third",
    });
  });

  it("treats a missing entry as absent rather than an error", () => {
    expect(readCached("<PROMPT-ID>", "commit:latest")).toBeUndefined();
  });

  it("treats a corrupt cache as empty", () => {
    fs.writeFileSync(path.join(directory, CACHE_FILENAME), "{not json");
    expect(readCached("<PROMPT-ID>", "commit:latest")).toBeUndefined();
  });

  // ===== What one pull does =====

  it("calls the API and seeds the cache on the first pull", async () => {
    const handle = new FakeHandle();
    await pull(handle);

    expect(handle.pulls).toBe(1);
    expect(readCached("<PROMPT-ID>", "commit:latest")).toBeDefined();
  });

  it("serves a later pull from the cache", async () => {
    await pull(new FakeHandle());
    const second = new FakeHandle();
    await pull(second);

    expect(second.pulls).toBe(0);
    expect(second.loaded).toMatchObject({ text: "Hello {name}" });
  });

  it("always calls the API with defaultToCache off", async () => {
    await pull(new FakeHandle());
    const second = new FakeHandle();
    await pull(second, { defaultToCache: false });

    expect(second.pulls).toBe(1);
  });

  it("neither reads nor writes the cache when refresh is 0", async () => {
    const handle = new FakeHandle();
    await pull(handle, { refresh: 0 });

    expect(handle.pulls).toBe(1);
    expect(fs.existsSync(path.join(directory, CACHE_FILENAME))).toBe(false);
  });

  it("calls the API with refresh 0 even with an entry cached", async () => {
    await pull(new FakeHandle());
    const second = new FakeHandle();
    await pull(second, { refresh: 0 });

    expect(second.pulls).toBe(1);
  });

  it("leaves the cache alone with writeToCache off", async () => {
    await pull(new FakeHandle(), { writeToCache: false });
    expect(fs.existsSync(path.join(directory, CACHE_FILENAME))).toBe(false);
  });

  it("serves the cached copy when the API cannot be reached", async () => {
    await pull(new FakeHandle());
    const offline = new FakeHandle(aPrompt(), true);
    await pull(offline, { defaultToCache: false });

    expect(offline.loaded).toMatchObject({ text: "Hello {name}" });
  });

  it("throws when the API fails and nothing is cached", async () => {
    await expect(pull(new FakeHandle(aPrompt(), true))).rejects.toThrow(
      /unreachable/,
    );
  });

  it("throws when the API fails and the fallback is off", async () => {
    await pull(new FakeHandle());
    await expect(
      pull(new FakeHandle(aPrompt(), true), {
        defaultToCache: false,
        fallbackToCache: false,
      }),
    ).rejects.toThrow(/unreachable/);
  });

  // ===== Starting and stopping the refresh =====

  it("stops refreshing on a later pull with refresh 0", async () => {
    const handle = new FakeHandle();
    await pull(handle);
    await pull(handle, { refresh: 0 });

    // Nothing is left scheduled, so the process can exit on its own.
    stopAllRefresh(handle);
    expect(handle.pulls).toBe(2);
  });
});
