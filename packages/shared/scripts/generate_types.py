#!/usr/bin/env python3
"""Generate the SDK wire types from the per-type OpenAPI specs in `types/`.

Each spec produces one Python module and one TypeScript module, so a shape is
declared once and both SDKs agree on it by construction.

Run it from the Python SDK's environment, which carries its PyYAML dependency
(`cd python && poetry install`).

    poetry run python ../packages/shared/scripts/generate_types.py            # write
    poetry run python ../packages/shared/scripts/generate_types.py --check    # verify (CI)

The specs are codegen-shaped: response schemas describe the `data` payload, and
enums are `$ref` components rather than inlined.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - dependency guidance only
    sys.exit(
        "generate_types.py needs PyYAML, which lives in the Python SDK's dev "
        "dependencies.\n"
        "Install it with `cd python && poetry install`, then run this script "
        "as\n`poetry run python ../packages/shared/scripts/generate_types.py`."
    )

REPO_ROOT = Path(__file__).resolve().parents[3]
SPEC_DIR = REPO_ROOT / "packages" / "shared" / "types"
SCRIPT_PATH = Path(__file__).resolve().relative_to(REPO_ROOT)

PYTHON_LINE_LENGTH = 80


@dataclass(frozen=True)
class Target:
    spec: str
    python_package: str
    typescript_directory: str

    @property
    def spec_path(self) -> Path:
        return SPEC_DIR / self.spec

    @property
    def python_path(self) -> Path:
        return REPO_ROOT / "python" / "confidentai" / self.python_package / "types.py"

    @property
    def typescript_path(self) -> Path:
        return REPO_ROOT / "typescript" / "src" / self.typescript_directory / "types.ts"


TARGETS: Tuple[Target, ...] = (
    Target(
        spec="prompts.yml",
        python_package="prompts",
        typescript_directory="prompts",
    ),
)

PRIMITIVES = {
    ("string", None): ("str", "string"),
    ("integer", None): ("int", "number"),
    ("number", None): ("float", "number"),
    ("boolean", None): ("bool", "boolean"),
}


class SpecError(Exception):
    """The spec cannot be generated from, and needs fixing."""


def snake_case(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def enum_member_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", str(value)).upper().strip("_")


@dataclass
class FieldType:
    """A resolved property type, and whether it admits absence or null."""

    python: str
    typescript: str
    nullable: bool = False

    def as_python(self, optional: bool) -> str:
        if optional or self.nullable:
            return f"Optional[{self.python}]"
        return self.python

    def as_typescript(self) -> str:
        return f"{self.typescript} | null" if self.nullable else self.typescript


@dataclass
class Field:
    name: str
    type: FieldType
    optional: bool

    @property
    def python_name(self) -> str:
        return snake_case(self.name)

    @property
    def needs_alias(self) -> bool:
        return self.python_name != self.name


@dataclass
class EnumType:
    name: str
    values: List[str]


@dataclass
class ObjectType:
    name: str
    fields: List[Field]
    open_ended: bool


def ref_name(ref: str) -> str:
    return ref.rsplit("/", 1)[1]


def strip_nullable(schema: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    """Reduce `oneOf: [X, {type: null}]` to `X` plus a nullable marker."""
    branches = schema.get("oneOf") or schema.get("anyOf")
    if not branches:
        return schema, False

    concrete = [b for b in branches if b.get("type") != "null"]
    nullable = len(concrete) != len(branches)
    if len(concrete) != 1:
        raise SpecError(
            f"unions of more than one concrete type are not supported: {schema}"
        )
    return concrete[0], nullable


def resolve_type(schema: Dict[str, Any], context: str) -> FieldType:
    schema, nullable = strip_nullable(schema)

    if "$ref" in schema:
        name = ref_name(schema["$ref"])
        return FieldType(name, name, nullable)

    schema_type = schema.get("type")

    if schema_type == "array":
        items = schema.get("items")
        if not items:
            raise SpecError(f"{context}: array without `items`")
        inner = resolve_type(items, f"{context}[]")
        return FieldType(
            f"List[{inner.python}]", f"{inner.as_typescript()}[]", nullable
        )

    if schema_type == "object":
        if schema.get("properties"):
            raise SpecError(
                f"{context}: inline object with properties. Promote it to a named "
                "schema under components.schemas so both SDKs get a stable type name."
            )
        return FieldType("Dict[str, Any]", "Record<string, unknown>", nullable)

    primitive = PRIMITIVES.get((schema_type, None))
    if primitive:
        return FieldType(primitive[0], primitive[1], nullable)

    raise SpecError(f"{context}: unsupported schema {schema}")


def parse_schemas(spec: Dict[str, Any]) -> Tuple[List[EnumType], List[ObjectType]]:
    schemas = spec.get("components", {}).get("schemas", {})
    enums: List[EnumType] = []
    objects: List[ObjectType] = []

    for name, schema in schemas.items():
        if "enum" in schema:
            enums.append(EnumType(name, list(schema["enum"])))
            continue

        if schema.get("type") != "object":
            raise SpecError(f"{name}: top-level schemas must be objects or enums")

        required = set(schema.get("required", []))
        properties = schema.get("properties", {})
        for field_name in required:
            if field_name not in properties:
                raise SpecError(
                    f"{name}.required names `{field_name}`, which is not a property"
                )

        fields = [
            Field(
                name=field_name,
                type=resolve_type(field_schema, f"{name}.{field_name}"),
                optional=field_name not in required,
            )
            for field_name, field_schema in properties.items()
        ]
        objects.append(
            ObjectType(
                name=name,
                fields=fields,
                open_ended=schema.get("additionalProperties") is not False,
            )
        )

    return enums, objects


def sort_by_dependency(objects: List[ObjectType]) -> List[ObjectType]:
    """Order objects so every type is declared before it is referenced."""
    by_name = {obj.name: obj for obj in objects}
    ordered: List[ObjectType] = []
    placed: set = set()

    def place(obj: ObjectType, seen: Tuple[str, ...]) -> None:
        if obj.name in placed:
            return
        if obj.name in seen:
            raise SpecError(
                f"circular reference: {' -> '.join(seen + (obj.name,))}"
            )
        for field in obj.fields:
            for dependency in re.findall(r"[A-Z][A-Za-z0-9]*", field.type.python):
                if dependency in by_name and dependency != obj.name:
                    place(by_name[dependency], seen + (obj.name,))
        placed.add(obj.name)
        ordered.append(obj)

    for obj in objects:
        place(obj, ())
    return ordered


def header(comment: str, spec_name: str) -> List[str]:
    return [
        f"{comment} Generated by {SCRIPT_PATH} from",
        f"{comment} {SPEC_DIR.relative_to(REPO_ROOT)}/{spec_name}. "
        "Do not edit by hand —",
        f"{comment} change the spec and regenerate.",
        "",
    ]


def wrap_python(prefix: str, arguments: List[str]) -> List[str]:
    single = f"{prefix}{', '.join(arguments)})"
    if len(single) <= PYTHON_LINE_LENGTH:
        return [single]
    lines = [prefix.rstrip()]
    for argument in arguments:
        lines.append(f"        {argument},")
    lines.append("    )")
    return lines


def render_python(
    enums: List[EnumType], objects: List[ObjectType], spec_name: str
) -> str:
    uses_optional = any(
        field.optional or field.type.nullable
        for obj in objects
        for field in obj.fields
    )
    uses_list = any(
        "List[" in field.type.python for obj in objects for field in obj.fields
    )
    uses_dict = any(
        "Dict[" in field.type.python for obj in objects for field in obj.fields
    )
    needs_field = any(field.needs_alias for obj in objects for field in obj.fields)

    typing_imports = [
        name
        for name, used in (
            ("Any", uses_dict),
            ("Dict", uses_dict),
            ("List", uses_list),
            ("Optional", uses_optional),
        )
        if used
    ]

    lines = header("#", spec_name)
    if enums:
        lines.append("from enum import Enum")
    if typing_imports:
        lines.append(f"from typing import {', '.join(typing_imports)}")
    lines.append("")
    if needs_field:
        lines.append("from pydantic import Field")
        lines.append("")
    lines.append("from ..types import ConfidentBaseModel")
    lines.append("")

    for enum in enums:
        lines.extend(["", f"class {enum.name}(Enum):"])
        for value in enum.values:
            lines.append(f'    {enum_member_name(value)} = "{value}"')
        lines.append("")

    for obj in objects:
        lines.extend(["", f"class {obj.name}(ConfidentBaseModel):"])
        if not obj.fields:
            lines.append("    pass")
            lines.append("")
            continue
        for field in obj.fields:
            annotation = field.type.as_python(field.optional)
            arguments = []
            if field.optional:
                arguments.append("default=None")
            if field.needs_alias:
                arguments.append(f'alias="{field.name}"')

            if not arguments:
                lines.append(f"    {field.python_name}: {annotation}")
            elif arguments == ["default=None"]:
                lines.append(f"    {field.python_name}: {annotation} = None")
            else:
                prefix = f"    {field.python_name}: {annotation} = Field("
                lines.extend(wrap_python(prefix, arguments))
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_typescript(
    enums: List[EnumType], objects: List[ObjectType], spec_name: str
) -> str:
    lines = header("//", spec_name)

    for enum in enums:
        lines.append(f"export enum {enum.name} {{")
        for value in enum.values:
            lines.append(f'  {enum_member_name(value)} = "{value}",')
        lines.extend(["}", ""])

    for obj in objects:
        lines.append(f"export interface {obj.name} {{")
        for field in obj.fields:
            optional = "?" if field.optional else ""
            lines.append(f"  {field.name}{optional}: {field.type.as_typescript()};")
        lines.extend(["}", ""])

    return "\n".join(lines).rstrip() + "\n"


def generate(target: Target) -> List[Tuple[Path, str]]:
    spec = yaml.safe_load(target.spec_path.read_text())
    enums, objects = parse_schemas(spec)
    objects = sort_by_dependency(objects)
    return [
        (target.python_path, render_python(enums, objects, target.spec)),
        (target.typescript_path, render_typescript(enums, objects, target.spec)),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero if any generated file is missing or stale",
    )
    arguments = parser.parse_args()

    stale: List[Path] = []
    written: List[Path] = []

    for target in TARGETS:
        try:
            outputs = generate(target)
        except SpecError as error:
            print(f"{target.spec}: {error}", file=sys.stderr)
            return 2

        for path, content in outputs:
            current = path.read_text() if path.exists() else None
            relative = path.relative_to(REPO_ROOT)
            if current == content:
                continue
            if arguments.check:
                stale.append(relative)
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            written.append(relative)

    if arguments.check:
        if stale:
            print("Generated types are stale:", file=sys.stderr)
            for path in stale:
                print(f"  {path}", file=sys.stderr)
            print(
                "\nRun `poetry run python ../packages/shared/scripts/generate_types.py` "
                "from python/ and commit the result.",
                file=sys.stderr,
            )
            return 1
        print("Generated types are up to date.")
        return 0

    for path in written:
        print(f"wrote {path}")
    if not written:
        print("no changes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
