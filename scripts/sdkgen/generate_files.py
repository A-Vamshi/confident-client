"""Where generated files go, and what they look like when they land.

The banner that marks a file as this generator's, the paths one resource
writes to, and the two formatters — black for Python, prettier for TypeScript
— that own line breaking so no renderer has to.
"""

import os
import posixpath
import re
import subprocess
import tempfile
import textwrap

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import black

from .constants import (
    GENERATED_MARKER,
    REPO_ROOT,
    TS_IDENTIFIER,
    PRETTIER_CONFIG,
    PYTHON_LINE_LENGTH,
    RESOURCE_MODULES,
    SCRIPT_PATH,
    TYPESCRIPT_ROOT,
)
from .errors import SpecError
from .openapi_helpers.openapi_to_sdk_names import camel_case


@dataclass(frozen=True)
class ResourcePaths:
    """A spec and the two modules it generates.

    The spec's filename is the resource name in both SDKs, so `datasets.yml`
    generates `confidentai/datasets/types.py` and `src/datasets/types.ts`.
    A kebab-cased spec becomes a snake_cased Python package, which is the only
    difference the two languages' import rules force.
    """

    name: str

    @property
    def module(self) -> str:
        return RESOURCE_MODULES.get(self.name, self.name)

    @property
    def python_module(self) -> str:
        return self.module.replace("-", "_")

    @property
    def python_path(self) -> Path:
        return (
            REPO_ROOT
            / "python"
            / "confidentai"
            / self.python_module
            / "types.py"
        )

    @property
    def typescript_path(self) -> Path:
        return REPO_ROOT / "typescript" / "src" / self.module / "types.ts"


def banner(comment: str, source: str) -> List[str]:
    return [
        f"{comment} {GENERATED_MARKER} by {SCRIPT_PATH} from",
        f"{comment} {source}.",
        f"{comment} Do not edit by hand — change the route in confident-cloud",
        f"{comment} and regenerate.",
        "",
    ]


def wrap_python(
    prefix: str, arguments: List[str], opener: str = ")"
) -> List[str]:
    single = f"{prefix}{', '.join(arguments)}{opener}"
    if len(single) <= PYTHON_LINE_LENGTH:
        return [single]
    if not opener:
        lines = [f"{prefix}("]
        for argument in arguments:
            lines.append(f"    {argument},")
        lines.append(")")
        return lines
    lines = [prefix.rstrip()]
    for argument in arguments:
        lines.append(f"        {argument},")
    lines.append("    )")
    return lines


def is_generated(text: str) -> bool:
    # Keyed to a marker rather than to this script's name, so renaming or
    # moving the generator does not make every generated file read as
    # hand-written and abort the next run.
    return GENERATED_MARKER in "\n".join(text.split("\n")[:3])


def format_python(source: str) -> str:
    """Hand the rendered module to black, so the format gate cannot disagree.

    Reimplementing black's line breaking here would leave two formatters to
    keep in step; the specs carry unions and literal sets long enough to make
    that a losing race.
    """
    return black.format_str(
        source, mode=black.Mode(line_length=PYTHON_LINE_LENGTH)
    )


def format_typescript(sources: Dict[str, str]) -> Dict[str, str]:
    """Hand every rendered module to prettier, in one pass.

    The same bargain `format_python` strikes with black: the renderers emit
    valid TypeScript on whatever lines are convenient and the formatter decides
    where it breaks, so there is only one thing that knows the house style.
    """
    if not sources:
        return {}
    if not PRETTIER_CONFIG.exists():
        raise SpecError(
            f"no prettier config at {PRETTIER_CONFIG}. Run `npm install` in "
            "typescript/ so generated TypeScript can be formatted."
        )

    with tempfile.TemporaryDirectory() as directory:
        staged = Path(directory)
        for name in sources:
            path = staged / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(sources[name])
        result = subprocess.run(
            [
                "npx",
                "prettier",
                "--config",
                str(PRETTIER_CONFIG),
                "--write",
                "--log-level",
                "warn",
                ".",
            ],
            cwd=staged,
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "NODE_PATH": str(TYPESCRIPT_ROOT / "node_modules"),
            },
        )
        if result.returncode != 0:
            raise SpecError(
                "prettier failed on the generated TypeScript:\n"
                f"{result.stderr.strip() or result.stdout.strip()}"
            )
        return {name: (staged / name).read_text() for name in sources}


def prose(text: Optional[str], width: int) -> List[str]:
    if not text:
        return []
    return textwrap.wrap(" ".join(text.split()), width=width)


def render_docstring(
    summary: str,
    description: Optional[str],
    arguments: List[Tuple[str, Optional[str]]],
    indent: str,
    descriptive: bool = True,
) -> List[str]:
    if not descriptive:
        return []
    width = PYTHON_LINE_LENGTH - len(indent)
    lines = [f'{indent}"""{summary}']

    description = prose(description, width)
    if description:
        lines.append("")
        lines.extend(f"{indent}{line}" for line in description)

    documented = [(name, text) for name, text in arguments if text]
    if documented:
        lines.extend(["", f"{indent}Args:"])
        for name, text in documented:
            wrapped = textwrap.wrap(
                f"{name}: {' '.join((text or '').split())}",
                width=width - 4,
                subsequent_indent="    ",
            )
            lines.extend(f"{indent}    {line}" for line in wrapped)

    lines.append(f'{indent}"""')
    return lines


def render_jsdoc(
    summary: str,
    description: Optional[str],
    arguments: List[Tuple[str, Optional[str]]],
    indent: str,
    descriptive: bool = True,
) -> List[str]:
    if not descriptive:
        return []
    width = PYTHON_LINE_LENGTH - len(indent) - 3
    lines = [f"{indent}/**", f"{indent} * {summary}"]
    described = prose(description, width)
    if described:
        lines.append(f"{indent} *")
        lines.extend(f"{indent} * {line}" for line in described)
    documented = [(name, text) for name, text in arguments if text]
    if documented:
        lines.append(f"{indent} *")
        for name, text in documented:
            wrapped = textwrap.wrap(
                f"@param {camel_case(name)} {' '.join((text or '').split())}",
                width=width,
                subsequent_indent="  ",
            )
            lines.extend(f"{indent} * {line}" for line in wrapped)
    lines.append(f"{indent} */")
    return lines


def typing_imports(annotations: Iterable[str]) -> List[str]:
    collected = list(annotations)
    return [
        name
        for name in ("Any", "Dict", "List", "Literal", "Optional", "Union")
        if any(
            re.search(rf"\b{name}\b", annotation) for annotation in collected
        )
    ]


def ts_import(source: str, target: str) -> str:
    """The specifier one generated file uses to reach another, both under src/."""
    relative = posixpath.relpath(
        target[: -len(".ts")], posixpath.dirname(source) or "."
    )
    return relative if relative.startswith(".") else f"./{relative}"


def ts_key(wire: str, value: str) -> str:
    """One entry of an options object, using shorthand where it reads the same."""
    if not TS_IDENTIFIER.match(wire):
        return f'"{wire}": {value}'
    return wire if wire == value else f"{wire}: {value}"
