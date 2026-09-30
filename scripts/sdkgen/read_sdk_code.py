"""Reading back what the rendered SDK declares: classes, methods, arguments.

What a caller can call is not quite what the spec describes: an overlay
rewrites a method after it is rendered, and a few are written by hand. So this
reads the code that ships rather than re-deriving it from the spec.

Python is parsed with `ast`. TypeScript has no parser here, so it is scanned
for the shapes the generator and prettier produce between them — every file it
reads is one those two wrote. A class or method it cannot read raises rather
than being skipped, because one left out reads as one that does not exist.
"""

import ast
import re

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from .errors import SpecError


@dataclass(frozen=True)
class RenderedParameter:
    """One argument, as the rendered source declares it."""

    name: str
    annotation: Optional[str]
    default: Optional[str]
    optional: bool
    # Python: after the bare `*`. TypeScript: a field of the trailing options
    # object. Either way the caller passes it by name.
    keyword: bool

    @property
    def required(self) -> bool:
        return not self.optional


@dataclass(frozen=True)
class RenderedMethod:
    name: str
    asynchronous: bool
    parameters: Tuple[RenderedParameter, ...]
    returns: Optional[str]
    doc: Optional[str]


@dataclass(frozen=True)
class RenderedClass:
    name: str
    doc: Optional[str]
    methods: Dict[str, RenderedMethod]
    fields: Tuple[Tuple[str, str], ...]
    # Exposed name against the hand-written function bound to it. Python only:
    # TypeScript declares a wrapper, which reads as an ordinary method.
    bindings: Dict[str, str]


# ===== Python =====


def _annotation(node: Optional[ast.AST]) -> Optional[str]:
    return None if node is None else ast.unparse(node).strip("\"'")


def _python_parameters(
    node: "ast.FunctionDef | ast.AsyncFunctionDef",
) -> Tuple[RenderedParameter, ...]:
    arguments = node.args
    positional = list(arguments.posonlyargs) + list(arguments.args)
    # Defaults are right-aligned against the positional arguments.
    padded: List[Optional[ast.expr]] = [None] * (
        len(positional) - len(arguments.defaults)
    ) + list(arguments.defaults)

    found: List[RenderedParameter] = []
    for argument, default in zip(positional, padded):
        if argument.arg == "self":
            continue
        found.append(
            RenderedParameter(
                name=argument.arg,
                annotation=_annotation(argument.annotation),
                default=_annotation(default),
                optional=default is not None,
                keyword=False,
            )
        )
    if arguments.vararg is not None:
        found.append(
            RenderedParameter(
                name=f"*{arguments.vararg.arg}",
                annotation=_annotation(arguments.vararg.annotation),
                default=None,
                optional=True,
                keyword=False,
            )
        )
    for argument, default in zip(arguments.kwonlyargs, arguments.kw_defaults):
        found.append(
            RenderedParameter(
                name=argument.arg,
                annotation=_annotation(argument.annotation),
                default=_annotation(default),
                optional=default is not None,
                keyword=True,
            )
        )
    if arguments.kwarg is not None:
        found.append(
            RenderedParameter(
                name=f"**{arguments.kwarg.arg}",
                annotation=_annotation(arguments.kwarg.annotation),
                default=None,
                optional=True,
                keyword=True,
            )
        )
    return tuple(found)


def _object_fields(node: ast.ClassDef) -> Tuple[Tuple[str, str], ...]:
    """What `__init__` assigns onto `self`, annotated, in source order."""
    for member in node.body:
        if (
            not isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef))
            or member.name != "__init__"
        ):
            continue
        return tuple(
            (statement.target.attr, _annotation(statement.annotation) or "")
            for statement in member.body
            if isinstance(statement, ast.AnnAssign)
            and isinstance(statement.target, ast.Attribute)
            and isinstance(statement.target.value, ast.Name)
            and statement.target.value.id == "self"
        )
    return ()


def _python_method(
    node: "ast.FunctionDef | ast.AsyncFunctionDef",
) -> RenderedMethod:
    return RenderedMethod(
        name=node.name,
        asynchronous=isinstance(node, ast.AsyncFunctionDef),
        parameters=_python_parameters(node),
        returns=_annotation(node.returns),
        doc=ast.get_docstring(node),
    )


def python_classes(source: str) -> Dict[str, RenderedClass]:
    """Every class one rendered Python module declares, by name."""
    found: Dict[str, RenderedClass] = {}
    for node in ast.parse(source).body:
        if not isinstance(node, ast.ClassDef):
            continue
        methods: Dict[str, RenderedMethod] = {}
        bindings: Dict[str, str] = {}
        for member in node.body:
            if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not member.name.startswith("_"):
                    methods[member.name] = _python_method(member)
            elif isinstance(member, ast.Assign) and isinstance(
                member.value, ast.Name
            ):
                bindings.update(
                    (target.id, member.value.id)
                    for target in member.targets
                    if isinstance(target, ast.Name)
                )
        found[node.name] = RenderedClass(
            name=node.name,
            doc=ast.get_docstring(node),
            methods=methods,
            fields=_object_fields(node),
            bindings=bindings,
        )
    return found


def python_functions(source: str) -> Dict[str, RenderedMethod]:
    """Every function a hand-written Python module declares at the top level."""
    return {
        node.name: _python_method(node)
        for node in ast.parse(source).body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def python_constants(source: str) -> Dict[str, str]:
    """Every module-level `NAME = "value"` a Python module declares.

    Read rather than restated, so a name the SDK resolves at runtime cannot
    drift from the copy published beside it.
    """
    found: Dict[str, str] = {}
    for node in ast.parse(source).body:
        if not isinstance(node, ast.Assign) or not isinstance(
            node.value, ast.Constant
        ):
            continue
        if not isinstance(node.value.value, str):
            continue
        found.update(
            (target.id, node.value.value)
            for target in node.targets
            if isinstance(target, ast.Name)
        )
    return found


# ===== TypeScript =====

# Prettier puts members at exactly one indent and closes a class in the first
# column, so this scans by indentation rather than matching braces through
# string literals and comments.
_CLASS = re.compile(r"^export\s+(?:abstract\s+)?class\s+([A-Za-z_$][\w$]*)")
_METHOD = re.compile(
    r"^  (?:(?P<access>private|protected|public)\s+)?(?:static\s+)?"
    r"(?:(?P<async>async)\s+)?(?:get\s+|set\s+)?(?P<name>[A-Za-z_$][\w$]*)\s*\("
)
_FIELD = re.compile(
    r"^  (?:readonly\s+)?(?P<name>[A-Za-z_$][\w$]*)(?P<optional>\?)?:\s*"
    r"(?P<annotation>.+);$"
)
_OPENERS = {"(": ")", "[": "]", "{": "}", "<": ">"}
_CLOSERS = {close: open for open, close in _OPENERS.items()}


def _depths(text: str) -> List[int]:
    """Nesting depth at each character, so a scan can stay at the top level."""
    depth = 0
    found: List[int] = []
    for index, character in enumerate(text):
        # `=>` is an arrow, not a closing angle bracket.
        if character in _CLOSERS and not (
            character == ">" and index and text[index - 1] == "="
        ):
            depth -= 1
        found.append(depth)
        if character in _OPENERS:
            depth += 1
    return found


def _split_top_level(text: str, separator: str) -> List[str]:
    depths = _depths(text)
    pieces: List[str] = []
    start = 0
    for index, character in enumerate(text):
        if character == separator and depths[index] == 0:
            pieces.append(text[start:index])
            start = index + 1
    pieces.append(text[start:])
    return [piece.strip() for piece in pieces if piece.strip()]


def _ts_parameter(text: str, keyword: bool = False) -> RenderedParameter:
    default: Optional[str] = None
    depths = _depths(text)
    for index, character in enumerate(text):
        if (
            character == "="
            and depths[index] == 0
            and text[index + 1 : index + 2] != ">"
            and text[index - 1 : index] not in ("=", "!", "<", ">")
        ):
            default = text[index + 1 :].strip()
            text = text[:index].strip()
            break

    name, colon, annotation = text.partition(":")
    if not colon:
        raise SpecError(
            f"cannot read the TypeScript parameter `{text}`: it declares no "
            "type. The generator's output moved; update sdkgen/read_sdk_code.py"
        )
    # A rest parameter keeps its dots: they are what a caller types.
    name = name.strip()
    optional = name.endswith("?")
    return RenderedParameter(
        name=name.rstrip("?"),
        annotation=annotation.strip(),
        default=default,
        optional=optional or default is not None,
        keyword=keyword,
    )


def _ts_parameters(text: str) -> Tuple[RenderedParameter, ...]:
    """A parameter list, with a trailing options object read as its fields.

    Past `TS_OPTIONS_THRESHOLD` the generator gathers a method's optionals into
    one object. Those stand for the arguments Python declares after its bare
    `*`, so they are read back as those rather than as one named `options`.
    """
    found: List[RenderedParameter] = []
    for piece in _split_top_level(text, ","):
        parameter = _ts_parameter(piece)
        annotation = parameter.annotation or ""
        if parameter.name != "options" or not annotation.startswith("{"):
            found.append(parameter)
            continue
        for entry in _split_top_level(annotation[1:-1], ";"):
            found.append(_ts_parameter(entry, keyword=True))
    return tuple(found)


def _ts_header(lines: Sequence[str], start: int) -> Tuple[str, int]:
    """One method's declaration, however many lines it takes."""
    pieces: List[str] = []
    depth = 0
    index = start
    while index < len(lines):
        line = lines[index]
        pieces.append(line.strip() if index > start else line)
        depth += line.count("(") - line.count(")")
        if depth <= 0:
            return " ".join(pieces), index
        index += 1
    raise SpecError(
        f"unterminated TypeScript method declaration at `{lines[start].strip()}`"
    )


def _ts_method(header: str, name: str, asynchronous: bool, doc: Optional[str]):
    opened = header.index("(")
    depths = _depths(header)
    closed = next(
        index
        for index in range(opened + 1, len(header))
        if header[index] == ")" and depths[index] == 0
    )
    rest = header[closed + 1 :].strip().rstrip("{").rstrip().rstrip(";")
    returns = rest[1:].strip() if rest.startswith(":") else None
    return RenderedMethod(
        name=name,
        asynchronous=asynchronous,
        parameters=_ts_parameters(header[opened + 1 : closed]),
        returns=returns,
        doc=doc,
    )


def _jsdoc(lines: Sequence[str]) -> str:
    """A JSDoc block as the prose it carries, tags and all, one per line."""
    prose: List[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped in ("/**", "*/"):
            continue
        prose.append(stripped.removeprefix("*").strip())
    return "\n".join(prose).strip()


def typescript_classes(source: str) -> Dict[str, RenderedClass]:
    """Every class one rendered TypeScript module declares, by name."""
    lines = source.split("\n")
    found: Dict[str, RenderedClass] = {}

    index = 0
    while index < len(lines):
        opening = _CLASS.match(lines[index])
        if not opening:
            index += 1
            continue

        methods: Dict[str, RenderedMethod] = {}
        fields: List[Tuple[str, str]] = []
        doc: Optional[str] = None
        index += 1
        while index < len(lines) and lines[index] != "}":
            line = lines[index]
            if line.strip().startswith("/**"):
                start = index
                while index < len(lines) and not lines[index].strip().endswith(
                    "*/"
                ):
                    index += 1
                doc = _jsdoc(lines[start : index + 1])
                index += 1
                continue

            method = _METHOD.match(line)
            if method:
                header, index = _ts_header(lines, index)
                name = method.group("name")
                public = method.group("access") in (None, "public")
                if (
                    public
                    and name != "constructor"
                    and not name.startswith("_")
                ):
                    methods[name] = _ts_method(
                        header, name, bool(method.group("async")), doc
                    )
                doc = None
                # Skip the body, so nothing inside it reads as a member.
                if header.rstrip().endswith("{"):
                    while index < len(lines) and lines[index] != "  }":
                        index += 1
                index += 1
                continue

            field = _FIELD.match(line)
            if field:
                fields.append(
                    (field.group("name"), field.group("annotation").strip())
                )
                doc = None
            index += 1

        found[opening.group(1)] = RenderedClass(
            name=opening.group(1),
            doc=None,
            methods=methods,
            fields=tuple(fields),
            bindings={},
        )
        index += 1

    return found


_FUNCTION = re.compile(
    r"^export\s+(?:(?P<async>async)\s+)?function\s+(?P<name>[A-Za-z_$][\w$]*)\s*\("
)


def typescript_functions(source: str) -> Dict[str, RenderedMethod]:
    """Every function a hand-written TypeScript module exports."""
    lines = source.split("\n")
    found: Dict[str, RenderedMethod] = {}
    index = 0
    while index < len(lines):
        declaration = _FUNCTION.match(lines[index])
        if not declaration:
            index += 1
            continue
        header, index = _ts_header(lines, index)
        found[declaration.group("name")] = _ts_method(
            header,
            declaration.group("name"),
            bool(declaration.group("async")),
            None,
        )
        index += 1
    return found
