/**
 * The handle methods no spec can describe.
 *
 * Each takes the stateful handle as its first argument and is called from the
 * generated class by name, so what a caller sees is the signature written here.
 */

import { PromptType } from "../common/types";
import { PromptInterpolationType, PromptMessage } from "../prompts/types";

const VARIABLE = "([a-zA-Z_][a-zA-Z0-9_]*)";

const PATTERNS: Partial<Record<PromptInterpolationType, RegExp>> = {
  [PromptInterpolationType.MUSTACHE]: new RegExp(
    `\\{\\{${VARIABLE}\\}\\}`,
    "g",
  ),
  [PromptInterpolationType.MUSTACHE_WITH_SPACE]: new RegExp(
    `\\{\\{ ${VARIABLE} \\}\\}`,
    "g",
  ),
  [PromptInterpolationType.FSTRING]: new RegExp(`\\{${VARIABLE}\\}`, "g"),
  [PromptInterpolationType.DOLLAR_BRACKETS]: new RegExp(
    `\\$\\{${VARIABLE}\\}`,
    "g",
  ),
};

export type InterpolatedPrompt = string | PromptMessage[];

interface PromptTemplate {
  type?: PromptType;
  interpolationType?: PromptInterpolationType;
  text?: string;
  messages?: PromptMessage[];
}

function substitute(
  text: string,
  interpolationType: PromptInterpolationType,
  values: Record<string, unknown>,
): string {
  const pattern = PATTERNS[interpolationType];
  if (!pattern) {
    // Jinja templates are rendered server-side, so a regex here would quietly
    // disagree with what the API produces for the same prompt.
    throw new Error(
      `${interpolationType} prompts cannot be interpolated by the SDK. ` +
        "Render the template with a Jinja engine instead.",
    );
  }
  return text.replace(pattern, (_match, variable: string) => {
    if (!(variable in values)) {
      throw new Error(`Missing variable in template: ${variable}`);
    }
    return String(values[variable]);
  });
}

/**
 * Render the prompt's template with `values`, without calling the API.
 *
 * Returns the interpolated text for a text prompt, and the interpolated
 * messages for a messages prompt.
 */
export function interpolatePrompt(
  prompt: PromptTemplate,
  values: Record<string, unknown>,
): InterpolatedPrompt {
  if (prompt.type === undefined || prompt.interpolationType === undefined) {
    throw new Error(
      "Prompt has no template to interpolate. Pull it first, or set its text " +
        "or messages.",
    );
  }

  if (prompt.type === PromptType.TEXT) {
    if (prompt.text === undefined) {
      throw new Error(
        `Prompt has type ${PromptType.TEXT} but no text to interpolate.`,
      );
    }
    return substitute(prompt.text, prompt.interpolationType, values);
  }

  if (prompt.messages === undefined) {
    throw new Error(
      `Prompt has type ${PromptType.LIST} but no messages to interpolate.`,
    );
  }
  return prompt.messages.map((message) => ({
    role: message.role,
    content: substitute(message.content, prompt.interpolationType!, values),
  }));
}
