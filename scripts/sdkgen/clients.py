"""Renders what calls the API: the endpoint enum, each resource's
operations, the client that composes them, and the mixin that hangs every
client off ConfidentAI.

Each renderer sits beside its twin in the other language, the way `Method`
keeps `signature` beside `ts_signature`. Keep them adjacent: it is the only
thing that makes a difference between the two SDKs visible in review.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from .constants import (
    API_VERSION_SEGMENT,
    ENDPOINTS_CLASS,
    METHOD_ORDER,
    OPERATIONS_MODULE,
    ORGANIZATION_KEY_RESOURCES,
    RESOURCE_MODULES,
    TS_OPERATIONS_MODULE,
)
from .core.errors import SpecError
from .core.naming import (
    camel_case,
    client_class_name,
    endpoint_member,
    endpoint_value,
    python_module_for,
    singular,
    snake_case,
    ts_module_for,
)
from .core.operations import resolve_method
from .core.output import (
    banner,
    format_python,
    render_docstring,
    render_jsdoc,
    ts_import,
    ts_key,
    typing_imports,
    wrap_python,
)
from .core.shapes import Resolver
from .core.spec import Route


# ===== The endpoint enum =====


def render_endpoints(
    resources: Dict[str, List[Route]], source: str, docs: bool = True
) -> str:
    members: Dict[str, Tuple[str, str]] = {}
    lines = banner("#", source)
    lines.extend(
        [
            "from enum import Enum",
            "",
            "",
            f"class {ENDPOINTS_CLASS}(Enum):",
        ]
    )

    for resource in sorted(resources):
        paths = sorted({route.path for route in resources[resource]})
        if docs:
            lines.append(f"    # {resource}")
        for path in paths:
            name = endpoint_member(path)
            value = endpoint_value(path)
            claimed = members.get(name)
            if claimed and claimed[1] != value:
                raise SpecError(
                    f"`{path}` and `{claimed[0]}` both name the endpoint "
                    f"member `{name}`. Rename one upstream."
                )
            members[name] = (path, value)
            lines.append(f'    {name} = "{value}"')
        lines.append("")

    return format_python("\n".join(lines).rstrip() + "\n")


def render_typescript_endpoints(
    resources: Dict[str, List[Route]], docs: bool = True
) -> str:
    lines = [f"export enum {ENDPOINTS_CLASS} {{"]
    for index, resource in enumerate(sorted(resources)):
        if index:
            lines.append("")
        if docs:
            lines.append(f"  // {resource}")
        for path in sorted({route.path for route in resources[resource]}):
            lines.append(
                f'  {endpoint_member(path)} = "{endpoint_value(path)}",'
            )
    lines.append("}")
    return "\n".join(lines)


# ===== Splitting a resource's routes into modules =====


def url_segments(route: Route) -> List[str]:
    """The path's literal segments, which are what nest the modules."""
    return [
        part
        for part in route.path.split("/")
        if part
        and not API_VERSION_SEGMENT.fullmatch(part)
        and not part.startswith("{")
    ]


@dataclass
class Group:
    """One module's worth of routes, and the groups nested below it."""

    name: str
    routes: List[Route]
    children: List["Group"]


def _collapse(name: str, node: Dict[str, Any]) -> Any:
    """A node, or the single route that stands in for it.

    Mirrors `toNavItem` in confident-landing's generate-v2-openapi.ts: a node
    holding one thing is not worth its own level, so a lone route is hoisted
    into the parent and a lone child is merged into this name.
    """
    routes = list(node["leaves"])
    children = []
    for child_name, child in sorted(node["children"].items()):
        item = _collapse(child_name, child)
        if isinstance(item, Group):
            children.append(item)
        else:
            routes.append(item)

    if len(routes) + len(children) == 1:
        if routes:
            return routes[0]
        only = children[0]
        return Group(f"{name}-{only.name}", only.routes, only.children)
    return Group(name, routes, children)


def resource_groups(routes: List[Route]) -> Group:
    root: Dict[str, Any] = {"leaves": [], "children": {}}
    for route in routes:
        node = root
        for segment in url_segments(route)[1:]:
            node = node["children"].setdefault(
                segment, {"leaves": [], "children": {}}
            )
        node["leaves"].append(route)

    collapsed = _collapse("", root)
    # `_collapse` hoists a lone route into its parent, but a resource
    # holding one route has no parent to hoist it into.
    if isinstance(collapsed, Route):
        return Group("", [collapsed], [])
    return collapsed


def flatten_groups(
    group: Group, prefix: Tuple[str, ...] = ()
) -> List[Tuple[Tuple[str, ...], List[Route]]]:
    path = prefix + ((group.name,) if group.name else ())
    found = [(path, group.routes)] if group.routes else []
    for child in group.children:
        found.extend(flatten_groups(child, path))
    return found


def group_module(segments: Tuple[str, ...]) -> str:
    directory = "/".join(snake_case(s.replace("-", "_")) for s in segments)
    return (
        f"{directory}/{OPERATIONS_MODULE}" if directory else OPERATIONS_MODULE
    )


def ts_group_module(segments: Tuple[str, ...]) -> str:
    directory = "/".join(segments)
    return (
        f"{directory}/{TS_OPERATIONS_MODULE}"
        if directory
        else TS_OPERATIONS_MODULE
    )


def group_class(
    resource: str, segments: Tuple[str, ...], acronyms: Set[str]
) -> str:
    """The class holding one module's operations.

    Named for the URL segments it covers, falling back to the resource for the
    group at the top of it — every resource has one of those, so naming it for
    its position would declare the same class in every nested resource. The
    resource is singularized so a tag that is already singular, like
    `organization`, reads the same as one that is not.
    """
    return client_class_name(
        "-".join(segments) or singular(resource), acronyms, "Operations"
    )


# ===== One module of operations =====


def render_client(
    resource: str,
    routes: List[Route],
    home: Dict[str, str],
    acronyms: Set[str],
    class_name: str,
    schemas: Dict[str, Any],
    owns_api: bool = True,
    docs: bool = True,
) -> Tuple[str, Set[str]]:
    resolver = Resolver(resource, home)
    referenced: Set[str] = set()
    annotations: List[str] = []
    body: List[str] = []

    ordered = sorted(
        routes, key=lambda route: (route.path, METHOD_ORDER.index(route.method))
    )
    for route in ordered:
        method = resolve_method(route, resolver, schemas)
        annotations.extend(method.annotations)
        referenced.update(method.referenced)
        signature = method.signature()

        for is_async in (False, True):
            prefix = "async def a_" if is_async else "def "
            caller = (
                "await self._api.a_request("
                if is_async
                else "self._api.request("
            )
            body.append("")
            body.append(
                f"    {prefix}{method.name}({', '.join(signature)}) -> "
                f"{method.returns}:"
            )
            body.extend(render_docstring(*method.prose, " " * 8, docs))
            body.append(f"        return {caller}")
            body.extend(f"            {line}" for line in method.call)
            body.append("        )")

    for owner, names in resolver.external.items():
        referenced.update(names)

    groups: Dict[str, List[str]] = {}
    for name in sorted(referenced):
        groups.setdefault(home[name], []).append(name)

    modules = {
        "confidentai.api": ["Api", "HttpMethods"],
        "confidentai.endpoints": [ENDPOINTS_CLASS],
    }
    for owner, names in groups.items():
        modules.setdefault(python_module_for(owner), []).extend(names)

    typing_names = typing_imports(annotations)
    lines = []
    if typing_names:
        lines.extend([f"from typing import {', '.join(typing_names)}", ""])
    for module in sorted(modules):
        lines.extend(
            wrap_python(
                f"from {module} import ", sorted(modules[module]), opener=""
            )
        )
    lines.extend(["", "", f"class {class_name}:"])
    if owns_api:
        lines.append("    def __init__(self, api: Api) -> None:")
        lines.append("        self._api = api")
    else:
        # The composed client assigns this; the mixin only ever reads it.
        lines.append("    _api: Api")
    lines.extend(body)

    if resolver.promoted_objects or resolver.promoted_enums:
        raise SpecError(
            f"{resource}: a parameter declares an inline shape, which has no "
            "generated type to name. Give it a $ref upstream."
        )
    return "\n".join(lines), referenced


def render_typescript_client(
    resource: str,
    routes: List[Route],
    home: Dict[str, str],
    acronyms: Set[str],
    class_name: str,
    schemas: Dict[str, Any],
    path: str,
    extends: Optional[Tuple[str, str]] = None,
    docs: bool = True,
) -> str:
    """One TypeScript class of methods, mirroring `render_client`."""
    resolver = Resolver(resource, home)
    referenced: Set[str] = set()
    body: List[str] = []

    ordered = sorted(
        routes, key=lambda route: (route.path, METHOD_ORDER.index(route.method))
    )
    for route in ordered:
        method = resolve_method(route, resolver, schemas)
        referenced.update(method.named_types)
        summary, description, documented = method.prose

        options = []
        if method.sends:
            if method.body_parameter:
                options.append(f"body: {camel_case(method.body_parameter)}")
            else:
                entries = ", ".join(
                    ts_key(p.wire, p.ts_name)
                    for p in method.parameters
                    if p.source == "body"
                )
                options.append(f"body: {{ {entries} }}")
        for source, key in (("path", "urlParams"), ("query", "params")):
            entries = ", ".join(
                ts_key(p.wire, p.ts_name)
                for p in method.parameters
                if p.source == source
            )
            if entries:
                options.append(f"{key}: {{ {entries} }}")

        call = [
            f"HttpMethods.{route.method.upper()},",
            f"{ENDPOINTS_CLASS}.{endpoint_member(route.path)},",
        ]
        if options:
            call.append(f"{{ {', '.join(options)} }},")

        body.append("")
        body.extend(render_jsdoc(summary, description, documented, "  ", docs))
        body.append(
            f"  async {method.ts_name}({', '.join(method.ts_signature())})"
            f": Promise<{method.ts_returns}> {{"
        )
        body.append(f"    return this.api.sendRequest<{method.ts_returns}>(")
        body.extend(f"      {line}" for line in call)
        body.append("    );")
        body.append("  }")

    for _, names in resolver.external.items():
        referenced.update(names)

    imports: Dict[str, List[str]] = {}
    for name in sorted(referenced):
        target = f"{ts_module_for(home[name])}/types.ts"
        imports.setdefault(ts_import(path, target), []).append(name)

    lines = []
    transport = ["HttpMethods"] + ([] if extends else ["Api"])
    lines.append(
        f"import {{ {', '.join(sorted(transport))} }} "
        f'from "{ts_import(path, "api.ts")}";'
    )
    lines.append(
        f'import {{ {ENDPOINTS_CLASS} }} from "{ts_import(path, "endpoints.ts")}";'
    )
    if extends:
        lines.append(f'import {{ {extends[0]} }} from "{extends[1]}";')
    for specifier in sorted(imports):
        lines.append(
            f"import {{ {', '.join(sorted(imports[specifier]))} }} "
            f'from "{specifier}";'
        )

    inherits = f" extends {extends[0]}" if extends else ""
    lines.extend(["", f"export class {class_name}{inherits} {{"])
    if not extends:
        lines.append("  constructor(protected readonly api: Api) {}")
        lines.extend(body)
    else:
        lines.extend(body[1:])
    lines.append("}")

    if resolver.promoted_objects or resolver.promoted_enums:
        raise SpecError(
            f"{resource}: a parameter declares an inline shape, which has no "
            "generated type to name. Give it a $ref upstream."
        )
    return "\n".join(lines)


# ===== The client that composes them, and every file a resource generates =====


def render_composition(
    resource: str,
    groups: List[Tuple[Tuple[str, ...], List[Route]]],
    acronyms: Set[str],
) -> str:
    """The class composing a resource's nested operation modules into one."""
    module = RESOURCE_MODULES.get(resource, resource).replace("-", "_")
    mixins = [
        (
            f"confidentai.{module}."
            + group_module(segments)[: -len(".py")].replace("/", "."),
            group_class(resource, segments, acronyms),
        )
        for segments, _ in groups
    ]

    lines = ["from confidentai.api import Api"]
    for path, name in mixins:
        lines.append(f"from {path} import {name}")
    lines.extend(
        [
            "",
            "",
            f"class {client_class_name(RESOURCE_MODULES.get(resource, resource), acronyms)}(",
        ]
    )
    for _, name in mixins:
        lines.append(f"    {name},")
    lines.extend(
        [
            "):",
            "    def __init__(self, api: Api) -> None:",
            "        self._api = api",
        ]
    )
    return "\n".join(lines)


def resource_client_files(
    resource: str,
    routes: List[Route],
    home: Dict[str, str],
    acronyms: Set[str],
    schemas: Dict[str, Any],
    docs: bool = True,
) -> List[Tuple[str, str]]:
    """(filename, source) for every client module one resource generates."""
    client = client_class_name(
        RESOURCE_MODULES.get(resource, resource), acronyms
    )
    groups = flatten_groups(resource_groups(routes))

    # A resource whose routes all sit at one level is one file. Splitting
    # it would leave a client.py composing a single mixin, which is pure
    # indirection.
    if len(groups) == 1:
        source, _ = render_client(
            resource, routes, home, acronyms, client, schemas, docs=docs
        )
        return [("client.py", source)]

    files = []
    for segments, group_routes in groups:
        source, _ = render_client(
            resource,
            group_routes,
            home,
            acronyms,
            group_class(resource, segments, acronyms),
            schemas,
            owns_api=False,
            docs=docs,
        )
        files.append((group_module(segments), source))
    files.append(("client.py", render_composition(resource, groups, acronyms)))
    return files


def ts_resource_client_files(
    resource: str,
    routes: List[Route],
    home: Dict[str, str],
    acronyms: Set[str],
    schemas: Dict[str, Any],
    docs: bool = True,
) -> List[Tuple[str, str]]:
    """(filename, source) for every TypeScript client module of one resource.

    TypeScript has no multiple inheritance, so the per-folder classes Python
    mixes into one client are chained instead: each extends the one before it,
    and the client extends the last. The call surface is the same flat set of
    methods either way.
    """
    client = client_class_name(
        RESOURCE_MODULES.get(resource, resource), acronyms
    )
    groups = flatten_groups(resource_groups(routes))
    directory = ts_module_for(resource)

    if len(groups) == 1:
        source = render_typescript_client(
            resource,
            routes,
            home,
            acronyms,
            client,
            schemas,
            f"{directory}/client.ts",
            docs=docs,
        )
        return [("client.ts", source)]

    files = []
    previous: Optional[Tuple[str, str]] = None
    for segments, group_routes in groups:
        module = ts_group_module(segments)
        path = f"{directory}/{module}"
        name = group_class(resource, segments, acronyms)
        extends = (
            (previous[0], ts_import(path, previous[1])) if previous else None
        )
        files.append(
            (
                module,
                render_typescript_client(
                    resource,
                    group_routes,
                    home,
                    acronyms,
                    name,
                    schemas,
                    path,
                    extends,
                    docs,
                ),
            )
        )
        previous = (name, path)

    assert previous is not None
    last, path = previous
    client_path = f"{directory}/client.ts"
    files.append(
        (
            "client.ts",
            "\n".join(
                [
                    f"import {{ {last} }} from "
                    f'"{ts_import(client_path, path)}";',
                    "",
                    f"export class {client} extends {last} {{}}",
                ]
            ),
        )
    )
    return files


# ===== The mixin that hangs every client off ConfidentAI =====


def render_generated_clients(
    resources: Dict[str, List[Route]], acronyms: Set[str]
) -> str:
    """The mixin that hangs every generated client off the root client."""
    modules = {
        resource: RESOURCE_MODULES.get(resource, resource).replace("-", "_")
        for resource in sorted(resources)
    }
    classes = {
        resource: client_class_name(
            RESOURCE_MODULES.get(resource, resource), acronyms
        )
        for resource in modules
    }

    lines = [
        "from typing import TYPE_CHECKING",
        "",
        "from confidentai.api import Api, ApiKeyKind",
        "",
        "if TYPE_CHECKING:",
    ]
    for resource, module in modules.items():
        lines.append(
            f"    from confidentai.{module}.client import {classes[resource]}"
        )
    lines.extend(
        [
            "",
            "",
            "class GeneratedClients:",
            "    def _api(self, key_kind: ApiKeyKind) -> Api:",
            "        raise NotImplementedError",
        ]
    )

    for resource, module in modules.items():
        kind = (
            "ORGANIZATION"
            if resource in ORGANIZATION_KEY_RESOURCES
            else "PROJECT"
        )
        lines.extend(
            [
                "",
                "    @property",
                f'    def {module}(self) -> "{classes[resource]}":',
                f"        from confidentai.{module}.client import "
                f"{classes[resource]}",
                "",
                f"        return {classes[resource]}("
                f"self._api(ApiKeyKind.{kind}))",
            ]
        )
    return "\n".join(lines)


def render_typescript_generated_clients(
    resources: Dict[str, List[Route]], acronyms: Set[str]
) -> str:
    """The base class that hangs every generated client off ConfidentAI."""
    directories = {
        resource: ts_module_for(resource) for resource in sorted(resources)
    }
    classes = {
        resource: client_class_name(
            RESOURCE_MODULES.get(resource, resource), acronyms
        )
        for resource in directories
    }

    lines = ['import { Api, ApiKeyKind } from "../api";']
    for resource, directory in directories.items():
        lines.append(
            f'import {{ {classes[resource]} }} from "../{directory}/client";'
        )
    lines.extend(
        [
            "",
            "export abstract class GeneratedClients {",
            "  protected abstract api(keyKind: ApiKeyKind): Api;",
        ]
    )
    for resource, directory in directories.items():
        kind = (
            "ORGANIZATION"
            if resource in ORGANIZATION_KEY_RESOURCES
            else "PROJECT"
        )
        lines.extend(
            [
                "",
                f"  get {camel_case(directory)}(): {classes[resource]} {{",
                f"    return new {classes[resource]}(this.api(ApiKeyKind.{kind}));",
                "  }",
            ]
        )
    lines.append("}")
    return "\n".join(lines)
