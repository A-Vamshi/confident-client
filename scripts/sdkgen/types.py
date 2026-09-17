"""Renders the wire types: a Python and a TypeScript module per resource."""

from typing import Any, Dict, List, Tuple

from .constants import (
    RESOURCE_MODULES,
    PYTHON_LINE_LENGTH,
)
from .core.errors import (
    SpecError,
)
from .core.naming import (
    enum_member_name,
    python_module_for,
)
from .core.spec import (
    split_union,
)
from .core.shapes import (
    AliasType,
    EnumType,
    Module,
    Resolver,
)
from .core.output import (
    format_python,
    banner,
    wrap_python,
)


def declare(
    resource: str,
    schemas: Dict[str, Any],
    home: Dict[str, str],
) -> Module:
    resolver = Resolver(resource, home)
    module = Module(resource=resource)

    for name, schema in schemas.items():
        if "enum" in schema:
            module.enums.append(EnumType(name, list(schema["enum"])))
            continue

        branches, nullable = split_union(schema)
        is_union = len(branches) > 1 or bool(
            schema.get("anyOf") or schema.get("oneOf")
        )
        if is_union:
            module.aliases.append(
                AliasType(name, resolver.resolve(schema, name, name))
            )
            continue

        if schema.get("type") != "object":
            raise SpecError(
                f"{name}: top-level schemas must be objects, enums, or unions"
            )

        module.objects.append(resolver.build_object(name, schema))

    module.objects.extend(resolver.promoted_objects)
    module.enums.extend(resolver.promoted_enums)
    module.imports = {
        owner: sorted(names)
        for owner, names in sorted(resolver.external.items())
    }
    return module


def sort_by_dependency(module: Module) -> None:
    """Order declarations so every type is declared before it is referenced."""
    declarations: Dict[str, Any] = {}
    for obj in module.objects:
        declarations[obj.name] = obj
    for alias in module.aliases:
        declarations[alias.name] = alias

    ordered: List[Any] = []
    placed: set = set()

    def place(declaration: Any, seen: Tuple[str, ...]) -> None:
        if declaration.name in placed:
            return
        if declaration.name in seen:
            raise SpecError(
                f"circular reference: {' -> '.join(seen + (declaration.name,))}"
            )
        for dependency in declaration.deps:
            if dependency in declarations and dependency != declaration.name:
                place(declarations[dependency], seen + (declaration.name,))
        placed.add(declaration.name)
        ordered.append(declaration)

    for declaration in list(module.objects) + list(module.aliases):
        place(declaration, ())

    module.declarations = ordered


def uses(module: Module, needle: str) -> bool:
    annotations = [
        item.type.python for obj in module.objects for item in obj.fields
    ] + [alias.type.python for alias in module.aliases]
    return any(needle in annotation for annotation in annotations)


def render_python(module: Module, source: str) -> str:
    uses_optional = any(
        item.optional or item.type.nullable
        for obj in module.objects
        for item in obj.fields
    ) or any(alias.type.nullable for alias in module.aliases)

    typing_imports = [
        name
        for name, used in (
            ("Any", uses(module, "Any")),
            ("Dict", uses(module, "Dict[")),
            ("List", uses(module, "List[")),
            ("Literal", uses(module, "Literal[")),
            ("Optional", uses_optional),
            ("Tuple", uses(module, "Tuple[")),
            ("Union", uses(module, "Union[")),
        )
        if used
    ]

    needs_field = any(
        item.needs_alias for obj in module.objects for item in obj.fields
    )

    first_party = [
        (python_module_for(owner), list(names))
        for owner, names in module.imports.items()
    ]
    first_party.append(("confidentai.types", ["ConfidentBaseModel"]))
    third_party = [("pydantic", ["Field"])] if needs_field else []

    lines = banner("#", source)
    if module.enums:
        lines.append("from enum import Enum")
    if typing_imports:
        lines.append(f"from typing import {', '.join(typing_imports)}")

    for group in (third_party, first_party):
        if not group:
            continue
        lines.append("")
        for name, names in sorted(group):
            lines.extend(wrap_python(f"from {name} import ", names, opener=""))

    # Each declaration below opens with one blank line of its own. ruff's
    # import rule wants two after the imports when a class comes first and one
    # when an assignment does, so the second is added only in the former case.
    first = next(iter(module.declarations), None)
    if module.enums or not isinstance(first, AliasType):
        lines.append("")

    for enum in module.enums:
        lines.extend(["", f"class {enum.name}(Enum):"])
        for value in enum.values:
            lines.append(f'    {enum_member_name(value)} = "{value}"')
        lines.append("")

    for declaration in module.declarations:
        if isinstance(declaration, AliasType):
            lines.extend(
                [
                    "",
                    f"{declaration.name} = {declaration.type.as_python(False)}",
                    "",
                ]
            )
            continue

        obj = declaration
        lines.extend(["", f"class {obj.name}(ConfidentBaseModel):"])
        if not obj.fields:
            lines.extend(["    pass", ""])
            continue
        for item in obj.fields:
            annotation = item.type.as_python(item.optional)
            arguments = []
            if item.optional:
                arguments.append("default=None")
            if item.needs_alias:
                arguments.append(f'alias="{item.name}"')

            declaration_line = f"    {item.python_name}: {annotation}"
            if not arguments:
                lines.append(declaration_line)
            elif arguments == ["default=None"]:
                lines.append(f"{declaration_line} = None")
            elif len(f"{declaration_line} = Field(") <= PYTHON_LINE_LENGTH:
                lines.extend(
                    wrap_python(f"{declaration_line} = Field(", arguments)
                )
            else:
                # A declaration too long to carry `Field(` wraps the whole
                # right-hand side, which is what the formatter does too.
                lines.append(f"{declaration_line} = (")
                lines.append("        Field(")
                lines.extend(
                    f"            {argument}," for argument in arguments
                )
                lines.append("        )")
                lines.append("    )")
        lines.append("")

    return format_python("\n".join(lines).rstrip() + "\n")


def render_python_barrel(module: Module, source: str) -> str:
    names = sorted(declaration.name for declaration in module.declarations)
    lines = banner("#", source)
    if not names:
        lines.append("__all__: list = []")
        return format_python("\n".join(lines) + "\n")

    lines.extend(
        wrap_python(
            f"from {python_module_for(module.resource)} import ", names, ""
        )
    )
    lines.append("")
    lines.append("__all__ = [")
    lines.extend(f'    "{name}",' for name in names)
    lines.append("]")
    return format_python("\n".join(lines) + "\n")


def render_typescript(module: Module, source: str) -> str:
    lines = banner("//", source)
    for owner, names in module.imports.items():
        directory = RESOURCE_MODULES.get(owner, owner)
        lines.append(
            f"import {{ {', '.join(names)} }} from \"../{directory}/types\";"
        )
    if module.imports:
        lines.append("")

    for enum in module.enums:
        lines.append(f"export enum {enum.name} {{")
        for value in enum.values:
            lines.append(f'  {enum_member_name(value)} = "{value}",')
        lines.extend(["}", ""])

    for declaration in module.declarations:
        if isinstance(declaration, AliasType):
            lines.extend(
                [
                    f"export type {declaration.name} = "
                    f"{declaration.type.as_typescript()};",
                    "",
                ]
            )
            continue

        obj = declaration
        lines.append(f"export interface {obj.name} {{")
        for item in obj.fields:
            optional = "?" if item.optional else ""
            lines.append(
                f"  {item.typescript_name}{optional}: "
                f"{item.type.as_typescript()};"
            )
        lines.extend(["}", ""])

    return "\n".join(lines).rstrip() + "\n"


def render_typescript_barrel(module: Module, source: str) -> str:
    """The `render_python_barrel` twin: `from "confidentai/datasets"` instead
    of `from "confidentai/datasets/types"`.

    `export *` carries exactly this resource's declarations, because a types
    module imports the shapes it shares without re-exporting them.
    """
    lines = banner("//", source)
    lines.append('export * from "./types";')
    return "\n".join(lines) + "\n"
