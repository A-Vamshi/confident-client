"""Turning a schema into a type both languages can declare.

`Resolver` is the heart of it: given any schema it returns a `FieldType` that
knows its own Python and TypeScript spelling and what it depends on. The
dataclasses above it are the model a renderer walks.
"""

from dataclasses import dataclass
from dataclasses import field
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from ..constants import (
    PRIMITIVES,
    PYDANTIC_RESERVED,
    TS_IDENTIFIER,
)
from .errors import SpecError
from .naming import pascal_case, singular, snake_case
from .spec import ref_name, split_union


@dataclass
class FieldType:
    python: str
    typescript: str
    nullable: bool = False
    deps: Tuple[str, ...] = ()
    # The two languages spell a boolean literal differently, so a literal's
    # members are carried per language rather than re-parsed out of `python`.
    literals: Tuple[Tuple[str, str], ...] = ()

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
        name = snake_case(self.name)
        return f"{name}_" if name in PYDANTIC_RESERVED else name

    @property
    def needs_alias(self) -> bool:
        return self.python_name != self.name

    @property
    def typescript_name(self) -> str:
        if TS_IDENTIFIER.match(self.name):
            return self.name
        return f'"{self.name}"'


@dataclass
class EnumType:
    name: str
    values: List[str]


@dataclass
class ObjectType:
    name: str
    fields: List[Field]

    @property
    def deps(self) -> Tuple[str, ...]:
        return tuple(dep for item in self.fields for dep in item.type.deps)


@dataclass
class AliasType:
    name: str
    type: FieldType

    @property
    def deps(self) -> Tuple[str, ...]:
        return self.type.deps


@dataclass
class Module:
    """Everything one generated module declares."""

    resource: str
    enums: List[EnumType] = field(default_factory=list)
    objects: List[ObjectType] = field(default_factory=list)
    aliases: List[AliasType] = field(default_factory=list)
    imports: Dict[str, List[str]] = field(default_factory=dict)
    declarations: List[Any] = field(default_factory=list)


def unique(values: Iterable[Any]) -> List[Any]:
    seen: List[Any] = []
    for value in values:
        if value not in seen:
            seen.append(value)
    return seen


def literal_value(value: Any) -> Tuple[str, str]:
    if isinstance(value, bool):
        return str(value), "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value), str(value)
    return f'"{value}"', f'"{value}"'


def literal_of(values: Sequence[Any], nullable: bool) -> FieldType:
    members = unique(literal_value(value) for value in values)
    return FieldType(
        f"Literal[{', '.join(python for python, _ in members)}]",
        " | ".join(typescript for _, typescript in members),
        nullable,
        (),
        tuple(members),
    )


def union_of(members: Sequence[FieldType], nullable: bool) -> FieldType:
    """Collapse branches into one annotation.

    Several branches often narrow the same primitive to different literals, so
    their values are merged into a single `Literal` rather than left as a union
    of unions.
    """
    literals: List[Tuple[str, str]] = []
    others_python: List[str] = []
    others_typescript: List[str] = []
    deps: List[str] = []

    for member in members:
        nullable = nullable or member.nullable
        deps.extend(member.deps)
        if member.literals:
            literals.extend(member.literals)
            continue
        others_python.append(member.python)
        others_typescript.append(member.as_typescript())

    merged = unique(literals)
    python = list(others_python)
    typescript = list(others_typescript)
    if merged:
        python.insert(0, f"Literal[{', '.join(p for p, _ in merged)}]")
        typescript.insert(0, " | ".join(t for _, t in merged))

    python = unique(python)
    typescript = unique(typescript)

    if len(python) == 1:
        return FieldType(
            python[0], typescript[0], nullable, tuple(deps), tuple(merged)
        )
    return FieldType(
        f"Union[{', '.join(python)}]",
        " | ".join(typescript),
        nullable,
        tuple(deps),
        tuple(merged),
    )


class Resolver:
    """Turns one spec's schemas into a module's declarations.

    Inline shapes the specs nest — an object with properties inside a property,
    an enum declared at its use site — have no name upstream, so they are
    promoted here to a name derived from where they sit. The name is a pure
    function of that position, so it is stable across runs.
    """

    def __init__(self, resource: str, home: Dict[str, str]) -> None:
        self.resource = resource
        self.home = home
        self.promoted_objects: List[ObjectType] = []
        self.promoted_enums: List[EnumType] = []
        self.external: Dict[str, List[str]] = {}
        self._promoted_names: Dict[str, Any] = {}

    def note_dependency(self, name: str) -> Tuple[str, ...]:
        owner = self.home.get(name)
        if owner is None:
            raise SpecError(
                f"reference to `{name}`, which no spec declares. The specs are "
                "generated together, so this means one was written by hand."
            )
        if owner == self.resource:
            return (name,)
        names = self.external.setdefault(owner, [])
        if name not in names:
            names.append(name)
        return ()

    def resolve(
        self, schema: Dict[str, Any], context: str, parent: str
    ) -> FieldType:
        branches, nullable = split_union(schema)

        if not branches:
            # A field the API documents as always null still has to exist on
            # the model, so it is typed as the only value it can hold.
            return FieldType("Any", "null", True)

        if len(branches) > 1:
            members = [
                self.resolve(branch, f"{context}|{index}", parent)
                for index, branch in enumerate(branches)
            ]
            return union_of(members, nullable)

        return self.resolve_single(branches[0], context, parent, nullable)

    def resolve_single(
        self,
        schema: Dict[str, Any],
        context: str,
        parent: str,
        nullable: bool,
    ) -> FieldType:
        if "$ref" in schema:
            name = ref_name(schema["$ref"])
            return FieldType(name, name, nullable, self.note_dependency(name))

        if not schema or set(schema) <= {"description", "example", "title"}:
            return FieldType("Any", "unknown", nullable)

        if "const" in schema:
            return literal_of([schema["const"]], nullable)

        if "enum" in schema:
            return self.resolve_inline_enum(schema, context, parent, nullable)

        schema_type = schema.get("type")

        if schema_type == "array":
            return self.resolve_array(schema, context, parent, nullable)

        if schema_type == "object":
            return self.resolve_object(schema, context, parent, nullable)

        primitive = PRIMITIVES.get(schema_type)
        if primitive:
            return FieldType(primitive[0], primitive[1], nullable)

        raise SpecError(f"{context}: unsupported schema {schema}")

    def resolve_inline_enum(
        self,
        schema: Dict[str, Any],
        context: str,
        parent: str,
        nullable: bool,
    ) -> FieldType:
        schema_type = schema.get("type")
        if schema_type in (None, "string", "integer", "number"):
            return literal_of(list(schema["enum"]), nullable)

        primitive = PRIMITIVES.get(schema_type)
        if not primitive:
            raise SpecError(
                f"{context}: enum of unsupported type {schema_type}"
            )
        return FieldType(primitive[0], primitive[1], nullable)

    def resolve_array(
        self,
        schema: Dict[str, Any],
        context: str,
        parent: str,
        nullable: bool,
    ) -> FieldType:
        if "prefixItems" in schema:
            members = [
                self.resolve(item, f"{context}[{index}]", parent)
                for index, item in enumerate(schema["prefixItems"])
            ]
            return FieldType(
                f"Tuple[{', '.join(m.python for m in members)}]",
                f"[{', '.join(m.as_typescript() for m in members)}]",
                nullable,
                tuple(dep for m in members for dep in m.deps),
            )

        items = schema.get("items")
        if not items:
            raise SpecError(
                f"{context}: array without `items` or `prefixItems`"
            )

        inner = self.resolve(items, f"{context}[]", parent)
        element = inner.as_typescript()
        if "|" in element or element.startswith("["):
            element = f"({element})"
        return FieldType(
            f"List[{inner.python}]",
            f"{element}[]",
            nullable,
            inner.deps,
        )

    def resolve_object(
        self,
        schema: Dict[str, Any],
        context: str,
        parent: str,
        nullable: bool,
    ) -> FieldType:
        if schema.get("properties"):
            name = self.promote_object(schema, context, parent)
            return FieldType(name, name, nullable, (name,))

        values = schema.get("additionalProperties")
        if isinstance(values, dict) and values:
            value = self.resolve(values, f"{context}{{}}", parent)
            return FieldType(
                f"Dict[str, {value.python}]",
                f"Record<string, {value.as_typescript()}>",
                nullable,
                value.deps,
            )
        return FieldType("Dict[str, Any]", "Record<string, unknown>", nullable)

    def promote_object(
        self, schema: Dict[str, Any], context: str, parent: str
    ) -> str:
        name = schema.get("title")
        name = pascal_case(name) if name else self.derive_name(context, parent)
        if name in self.home:
            raise SpecError(
                f"{context}: this inline object takes the name `{name}`, which "
                f"{self.home[name]}.yml already declares. Give the inline "
                "shape a distinct `title` upstream."
            )
        promoted = self._promoted_names.get(name)
        if promoted is None:
            self._promoted_names[name] = schema
            self.promoted_objects.append(self.build_object(name, schema))
        elif promoted != schema:
            raise SpecError(
                f"{context}: two different inline objects both take the name "
                f"`{name}`. Give one of them a distinct `title` upstream."
            )
        return name

    def derive_name(self, context: str, parent: str) -> str:
        leaf = context.split(".")[-1]
        depth = leaf.count("[]")
        leaf = leaf.replace("[]", "")
        stem = pascal_case(leaf)
        if depth:
            stem = singular(stem)
        return f"{parent}{stem}"

    def build_object(self, name: str, schema: Dict[str, Any]) -> ObjectType:
        required = set(schema.get("required", []))
        properties = schema.get("properties") or {}
        missing = sorted(required - set(properties))
        if missing:
            raise SpecError(
                f"{name}.required names {', '.join(missing)}, which "
                "are not properties"
            )
        fields = [
            Field(
                name=field_name,
                type=self.resolve(field_schema, f"{name}.{field_name}", name),
                optional=field_name not in required,
            )
            for field_name, field_schema in properties.items()
        ]
        return ObjectType(name=name, fields=fields)
