"""The handle methods no spec can describe.

Each takes the stateful handle as its first argument and is bound onto the
generated class by name, so what a caller sees is the signature written here.
"""

import re

from typing import Any, Dict, List, Pattern, Union

from confidentai.common.types import PromptType
from confidentai.prompts.types import PromptInterpolationType, PromptMessage

_VARIABLE = r"([a-zA-Z_][a-zA-Z0-9_]*)"

_PATTERNS: Dict[PromptInterpolationType, Pattern[str]] = {
    PromptInterpolationType.MUSTACHE: re.compile(r"\{\{" + _VARIABLE + r"\}\}"),
    PromptInterpolationType.MUSTACHE_WITH_SPACE: re.compile(
        r"\{\{ " + _VARIABLE + r" \}\}"
    ),
    PromptInterpolationType.FSTRING: re.compile(r"\{" + _VARIABLE + r"\}"),
    PromptInterpolationType.DOLLAR_BRACKETS: re.compile(
        r"\$\{" + _VARIABLE + r"\}"
    ),
}

InterpolatedPrompt = Union[str, List[PromptMessage]]


def _substitute(
    text: str,
    interpolation_type: PromptInterpolationType,
    values: Dict[str, Any],
) -> str:
    pattern = _PATTERNS.get(interpolation_type)
    if pattern is None:
        # Jinja templates are rendered server-side, so a regex here would
        # quietly disagree with what the API produces for the same prompt.
        raise ValueError(
            f"{interpolation_type.value} prompts cannot be interpolated by "
            "the SDK. Render the template with a Jinja engine instead."
        )

    def replace(match: "re.Match[str]") -> str:
        variable = match.group(1)
        if variable not in values:
            raise KeyError(f"Missing variable in template: {variable}")
        return str(values[variable])

    return pattern.sub(replace, text)


def interpolate_prompt(prompt: Any, **values: Any) -> InterpolatedPrompt:
    """Render the prompt's template with `values`, without calling the API.

    Returns the interpolated text for a text prompt, and the interpolated
    messages for a messages prompt.
    """
    if prompt.type is None or prompt.interpolation_type is None:
        raise ValueError(
            "Prompt has no template to interpolate. Pull it first, or set its "
            "text or messages."
        )

    if prompt.type is PromptType.TEXT:
        if prompt.text is None:
            raise ValueError(
                f"Prompt has type {PromptType.TEXT.value} but no text to "
                "interpolate."
            )
        return _substitute(prompt.text, prompt.interpolation_type, values)

    if prompt.messages is None:
        raise ValueError(
            f"Prompt has type {PromptType.LIST.value} but no messages to "
            "interpolate."
        )
    return [
        PromptMessage(
            role=message.role,
            content=_substitute(
                message.content, prompt.interpolation_type, values
            ),
        )
        for message in prompt.messages
    ]
