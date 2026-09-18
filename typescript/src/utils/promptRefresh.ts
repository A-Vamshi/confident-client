import { Prompt as PromptPayload } from "../prompts/types";

/** How a caller picked the commit to pull. */
export interface PromptSelector {
  commit?: string;
  version?: string;
  label?: string;
  branch?: string;
}

/** What refreshing needs of a prompt handle. */
export interface RefreshablePrompt {
  promptId?: string;
  pullOnce(options: PromptSelector): Promise<PromptPayload>;
  load(payload: PromptPayload): void;
}

/** What a finished refresh hands its result to. */
export type RefreshedHandler = (
  promptId: string,
  key: string,
  payload: PromptPayload,
) => void;

/**
 * How far a repeatedly failing refresh backs off. A prompt whose project lost
 * its API key would otherwise call a failing route every interval forever.
 */
const MAX_BACKOFF = 8;

const intervals = new WeakMap<RefreshablePrompt, Map<string, number>>();

function registryFor(prompt: RefreshablePrompt): Map<string, number> {
  let registry = intervals.get(prompt);
  if (!registry) {
    registry = new Map();
    intervals.set(prompt, registry);
  }
  return registry;
}

/**
 * Refresh `prompt` from `selector` every `everySeconds` seconds.
 *
 * Starting a refresh that is already running only retunes it: each tick reads
 * the interval again, so a later pull can change the rate without stacking a
 * second timer on the same selector.
 */
export function startRefresh(
  prompt: RefreshablePrompt,
  key: string,
  selector: PromptSelector,
  everySeconds: number,
  onRefreshed: RefreshedHandler,
): void {
  const registry = registryFor(prompt);
  const running = registry.has(key);
  registry.set(key, everySeconds);
  if (running) return;
  schedule(new WeakRef(prompt), key, { ...selector }, 0, onRefreshed);
}

/** Stop refreshing one selector. The timer ends on its next tick. */
export function stopRefresh(prompt: RefreshablePrompt, key: string): void {
  intervals.get(prompt)?.delete(key);
}

/** Stop refreshing every selector this handle pulled. */
export function stopAllRefresh(prompt: RefreshablePrompt): void {
  intervals.get(prompt)?.clear();
}

function schedule(
  reference: WeakRef<RefreshablePrompt>,
  key: string,
  selector: PromptSelector,
  failures: number,
  onRefreshed: RefreshedHandler,
): void {
  const prompt = reference.deref();
  if (!prompt) return;
  const interval = intervals.get(prompt)?.get(key);
  if (interval === undefined) return;

  const delay = interval * Math.min(2 ** failures, MAX_BACKOFF) * 1000;
  const timer = setTimeout(() => {
    void tick(reference, key, selector, failures, onRefreshed);
  }, delay);
  // A prompt waiting to refresh must not be what keeps the process running.
  timer.unref?.();
}

async function tick(
  reference: WeakRef<RefreshablePrompt>,
  key: string,
  selector: PromptSelector,
  failures: number,
  onRefreshed: RefreshedHandler,
): Promise<void> {
  const prompt = reference.deref();
  if (!prompt || !intervals.get(prompt)?.has(key)) return;

  let nextFailures = failures;
  try {
    const payload = await prompt.pullOnce(selector);
    if (prompt.promptId !== undefined) {
      onRefreshed(prompt.promptId, key, payload);
    }
    nextFailures = 0;
  } catch (error) {
    nextFailures += 1;
    console.warn(
      `Could not refresh the prompt (${key}); keeping the copy in hand ` +
        `and trying again later.`,
      error,
    );
  }
  schedule(reference, key, selector, nextFailures, onRefreshed);
}
