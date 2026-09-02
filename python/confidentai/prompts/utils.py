import re
from typing import Any, Dict, List, Optional, Pattern, Union

from .types import Prompt, PromptInterpolationType, PromptMessage, PromptType

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

Interpolated = Union[str, List[PromptMessage]]


def interpolate_text(
    text: str,
    interpolation_type: PromptInterpolationType,
    values: Dict[str, Any],
) -> str:
    def substitute(match: "re.Match[str]") -> str:
        variable = match.group(1)
        if variable not in values:
            raise KeyError(f"Missing variable in template: {variable}")
        return str(values[variable])

    return _PATTERNS[interpolation_type].sub(substitute, text)


def interpolate(
    prompt_type: Optional[PromptType],
    interpolation_type: Optional[PromptInterpolationType],
    values: Dict[str, Any],
    *,
    text: Optional[str] = None,
    messages: Optional[List[PromptMessage]] = None,
) -> Interpolated:
    if prompt_type is None or interpolation_type is None:
        raise ValueError(
            "Prompt has no template to interpolate. Pull it first, or set its "
            "text or messages."
        )

    if prompt_type is PromptType.TEXT:
        if text is None:
            raise ValueError(
                f"Prompt has type {PromptType.TEXT.value} but no text to "
                "interpolate."
            )
        return interpolate_text(text, interpolation_type, values)

    if messages is None:
        raise ValueError(
            f"Prompt has type {PromptType.LIST.value} but no messages to "
            "interpolate."
        )
    return [
        PromptMessage(
            role=message.role,
            content=interpolate_text(
                message.content, interpolation_type, values
            ),
        )
        for message in messages
    ]


def interpolate_prompt(prompt: Prompt, values: Dict[str, Any]) -> Interpolated:
    return interpolate(
        prompt.type,
        prompt.interpolation_type,
        values,
        text=prompt.text,
        messages=prompt.messages,
    )
