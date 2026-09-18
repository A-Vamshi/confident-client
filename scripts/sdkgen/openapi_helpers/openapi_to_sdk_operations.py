"""One operation of the spec, as both languages will spell it.

`resolve_method` reads a route once and returns a `Method` carrying every
argument in Python and TypeScript form. Every renderer reads that same
object, which is what stops the two SDKs drifting apart.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from ..constants import (
    TS_OPTIONS_THRESHOLD,
    ENDPOINTS_CLASS,
    PATH_PARAMETER,
    TS_RESERVED,
    UNION_BODY_PARAMETERS,
)
from ..errors import SpecError
from .openapi_to_sdk_names import (
    camel_case,
    endpoint_member,
    method_name,
    pascal_case,
    python_module_for,
    snake_case,
)
from .openapi_to_sdk_types import Resolver
from .openapi_parser import Route, ref_name, split_union


def parameters_in(route: Route, location: str) -> List[Dict[str, Any]]:
    declared = list(route.shared.get("parameters") or []) + list(
        route.operation.get("parameters") or []
    )
    return [param for param in declared if param.get("in") == location]


def path_parameters(route: Route) -> List[Dict[str, Any]]:
    """The path's parameters, in the order the path names them."""
    declared = {param["name"]: param for param in parameters_in(route, "path")}
    ordered = []
    for name in PATH_PARAMETER.findall(route.path):
        if name not in declared:
            raise SpecError(
                f"{route.operation_id}: `{route.path}` names `{name}`, which "
                "the operation does not declare as a parameter."
            )
        ordered.append(declared[name])
    return ordered


def response_type(route: Route) -> Tuple[str, bool]:
    """The schema a success response returns, and whether it may be null."""
    responses = route.operation.get("responses") or {}
    for code in sorted(responses):
        if not code.startswith("2"):
            continue
        content = (responses[code].get("content") or {}).get(
            "application/json"
        ) or {}
        data = ((content.get("schema") or {}).get("properties") or {}).get(
            "data"
        ) or {}
        if "$ref" in data:
            return ref_name(data["$ref"]), False

        branches, nullable = split_union(data)
        if nullable and len(branches) == 1 and "$ref" in branches[0]:
            return ref_name(branches[0]["$ref"]), True

        raise SpecError(
            f"{route.operation_id}: the {code} response does not carry `data` "
            "as a reference to a component schema."
        )
    raise SpecError(f"{route.operation_id}: no success response to return.")


def request_type(route: Route) -> Optional[str]:
    body = route.operation.get("requestBody") or {}
    schema = ((body.get("content") or {}).get("application/json") or {}).get(
        "schema"
    ) or {}
    if not schema:
        return None
    if "$ref" not in schema:
        raise SpecError(
            f"{route.operation_id}: the request body is not a reference to a "
            "component schema."
        )
    return ref_name(schema["$ref"])


def body_fields(
    name: str, schemas: Dict[str, Any]
) -> Optional[List[Dict[str, Any]]]:
    """A body's properties, or None when it is a union with no one shape.

    A union's branches declare different fields, so flattening them would let
    a caller mix two branches into a payload the API rejects.
    """
    schema = schemas.get(name) or {}
    if schema.get("anyOf") or schema.get("oneOf"):
        return None
    required = set(schema.get("required") or [])
    return [
        {"name": field, "schema": value, "required": field in required}
        for field, value in (schema.get("properties") or {}).items()
    ]


def union_body_help(
    name: str, schemas: Dict[str, Any], home: Dict[str, str]
) -> str:
    schema = schemas.get(name) or {}
    branches = [
        ref_name(branch["$ref"])
        for branch in schema.get("anyOf") or []
        if "$ref" in branch
    ]
    modules = sorted(
        {python_module_for(home[b]) for b in branches if b in home}
    )
    if len(branches) == 2:
        listed = f"a {branches[0]} or a {branches[1]}"
    else:
        listed = "one of " + ", ".join(branches)
    where = f", from {' and '.join(modules)}" if modules else ""
    return " ".join(
        part
        for part in (schema.get("description"), f"Pass {listed}{where}.")
        if part
    )


@dataclass(frozen=True)
class Parameter:
    """One argument of a generated method, and where the spec put it.

    Both languages' spellings are carried together so the two SDKs cannot
    disagree about what an operation takes.
    """

    name: str
    annotation: str
    typescript: str
    source: str
    wire: str
    keyword: bool
    required: bool

    @property
    def ts_name(self) -> str:
        name = camel_case(self.name)
        return f"{name}_" if name in TS_RESERVED else name

    def declaration(self) -> str:
        if self.keyword and not self.required:
            return f"{self.name}: {self.annotation} = None"
        return f"{self.name}: {self.annotation}"

    def ts_declaration(self) -> str:
        optional = "?" if not self.required else ""
        return f"{self.ts_name}{optional}: {self.typescript}"


@dataclass(frozen=True)
class Method:
    """One operation as Python, before any renderer decides how to call it.

    Every renderer that exposes an operation reads its surface from here, so a
    stateful handle cannot drift from the stateless method it delegates to.
    """

    route: Route
    name: str
    returns: str
    ts_returns: str
    sends: Optional[str]
    body_parameter: Optional[str]
    parameters: List[Parameter]
    documented: List[Tuple[str, Optional[str]]]
    call: List[str]
    annotations: List[str]
    referenced: Set[str]

    @property
    def named_types(self) -> Set[str]:
        """The types a caller of this method names.

        A flattened body's schema is the transport's business, so it drops out
        for any renderer that delegates rather than sends.
        """
        if self.sends and not self.body_parameter:
            return self.referenced - {self.sends}
        return self.referenced

    @property
    def prose(
        self,
    ) -> Tuple[str, Optional[str], List[Tuple[str, Optional[str]]]]:
        """The docstring's three parts, as `render_docstring` takes them."""
        return (
            self.route.operation.get("summary") or self.route.operation_id,
            self.route.operation.get("description"),
            self.documented,
        )

    @property
    def ts_name(self) -> str:
        return camel_case(self.name)

    def signature(self, skip: Sequence[str] = ()) -> List[str]:
        arguments = ["self"]
        kept = [p for p in self.parameters if p.name not in skip]
        arguments += [p.declaration() for p in kept if not p.keyword]
        keyword = [p.declaration() for p in kept if p.keyword]
        if keyword:
            arguments.append("*")
            arguments += keyword
        return arguments

    def ts_optional(self, skip: Sequence[str] = ()) -> List["Parameter"]:
        return [
            p for p in self.parameters if p.name not in skip and not p.required
        ]

    def ts_takes_options(self, skip: Sequence[str] = ()) -> bool:
        """Whether the optionals are gathered into a trailing object.

        TypeScript carries optionality in the argument order, so a method with
        several optionals makes a caller pass `undefined` for each one it is
        skipping. Past `TS_OPTIONS_THRESHOLD` they become one named object.
        """
        return len(self.ts_optional(skip)) >= TS_OPTIONS_THRESHOLD

    def ts_signature(self, skip: Sequence[str] = ()) -> List[str]:
        """Required arguments in path order, then whatever is optional."""
        kept = [p for p in self.parameters if p.name not in skip]
        required = [p.ts_declaration() for p in kept if p.required]
        optional = self.ts_optional(skip)
        if not self.ts_takes_options(skip):
            return required + [p.ts_declaration() for p in optional]
        fields = "; ".join(p.ts_declaration() for p in optional)
        return required + [f"options: {{ {fields} }} = {{}}"]

    def ts_unpacking(self, skip: Sequence[str] = ()) -> List[str]:
        """Binds a trailing options object back to the bare names the body uses.

        One line, so that everything below it reads the same whichever form the
        signature took.
        """
        if not self.ts_takes_options(skip):
            return []
        names = ", ".join(p.ts_name for p in self.ts_optional(skip))
        return [f"const {{ {names} }} = options;"]


def resolve_method(
    route: Route,
    resolver: Resolver,
    schemas: Dict[str, Any],
) -> Method:
    name = method_name(route.operation_id, route.resource)
    returns, optional = response_type(route)
    returns_annotation = f"Optional[{returns}]" if optional else returns
    ts_returns = f"{returns} | null" if optional else returns
    sends = request_type(route)
    annotations: List[str] = [returns_annotation]
    referenced: Set[str] = {returns} | ({sends} if sends else set())
    fields = body_fields(sends, schemas) if sends else None

    body_parameter = None
    if sends and fields is None:
        body_parameter = UNION_BODY_PARAMETERS.get(sends)
        if body_parameter is None:
            raise SpecError(
                f"{route.operation_id}: `{sends}` is a union, so its "
                "fields cannot be flattened. Name its parameter in "
                "UNION_BODY_PARAMETERS."
            )

    paths = path_parameters(route)
    queries = parameters_in(route, "query")
    resolved_queries = []
    for param in queries:
        resolved = resolver.resolve(
            param.get("schema") or {},
            f"{route.operation_id}.{param['name']}",
            pascal_case(route.operation_id),
        )
        referenced.update(resolved.deps)
        required = bool(param.get("required"))
        annotations.append(resolved.as_python(not required))
        resolved_queries.append(
            (
                param,
                resolved.as_python(not required),
                resolved.as_typescript(),
                required,
            )
        )
    resolved_queries.sort(key=lambda entry: not entry[3])

    resolved_body = []
    for field in fields or []:
        resolved = resolver.resolve(
            field["schema"],
            f"{route.operation_id}.{field['name']}",
            pascal_case(route.operation_id),
        )
        referenced.update(resolved.deps)
        annotations.append(resolved.as_python(not field["required"]))
        resolved_body.append(
            (
                field,
                resolved.as_python(not field["required"]),
                resolved.as_typescript(),
                field["required"],
            )
        )
    resolved_body.sort(key=lambda entry: not entry[3])

    documented: List[Tuple[str, Optional[str]]] = [
        (snake_case(param["name"]), param.get("description")) for param in paths
    ]
    if body_parameter:
        documented.append(
            (body_parameter, union_body_help(sends, schemas, resolver.home))
        )
    documented.extend(
        (snake_case(field["name"]), field["schema"].get("description"))
        for field, _, _, _ in resolved_body
    )
    documented.extend(
        (snake_case(param["name"]), param.get("description"))
        for param, _, _, _ in resolved_queries
    )

    parameters = [
        Parameter(
            snake_case(p["name"]),
            "str",
            "string",
            "path",
            p["name"],
            False,
            True,
        )
        for p in paths
    ]
    if body_parameter:
        parameters.append(
            Parameter(
                body_parameter, sends, sends, "union-body", sends, False, True
            )
        )
    parameters += [
        Parameter(
            snake_case(field["name"]),
            annotation,
            typescript,
            "body",
            field["name"],
            not required,
            required,
        )
        for field, annotation, typescript, required in resolved_body
    ]
    parameters += [
        Parameter(
            snake_case(param["name"]),
            annotation,
            typescript,
            "query",
            param["name"],
            True,
            required,
        )
        for param, annotation, typescript, required in resolved_queries
    ]

    call = [
        f"HttpMethods.{route.method.upper()},",
        f"{ENDPOINTS_CLASS}.{endpoint_member(route.path)},",
        f"response_schema={returns_annotation},",
    ]
    if sends:
        call.append(f"request_schema={sends},")
        if body_parameter:
            call.append(f"body={body_parameter},")
        else:
            entries = ", ".join(
                f'"{field["name"]}": {snake_case(field["name"])}'
                for field, _, _, _ in resolved_body
            )
            call.append(f"body={{{entries}}},")
    if paths:
        entries = ", ".join(
            f'"{p["name"]}": {snake_case(p["name"])}' for p in paths
        )
        call.append(f"path={{{entries}}},")
    if queries:
        entries = ", ".join(
            f'"{param["name"]}": {snake_case(param["name"])}'
            for param in queries
        )
        call.append(f"query={{{entries}}},")

    return Method(
        route=route,
        name=name,
        returns=returns_annotation,
        ts_returns=ts_returns,
        sends=sends,
        body_parameter=body_parameter,
        parameters=parameters,
        documented=documented,
        call=call,
        annotations=annotations,
        referenced=referenced,
    )
