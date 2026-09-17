"""Reading the OpenAPI document.

Which routes the SDK generates, which module owns each schema, and the small
vocabulary for walking a `$ref`. Nothing here knows what Python or TypeScript
look like.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Set, Tuple

from ..constants import (
    COMMON_RESOURCE,
    COMPONENT_REF,
    EXCLUDED_OPERATIONS,
    GENERATED_OPERATIONS,
    GENERATED_RESOURCES,
    METHODS,
    SCHEMA_REF,
    WRITABLE_SCHEMAS,
)
from .errors import SpecError


def ref_name(ref: str) -> str:
    if not ref.startswith(SCHEMA_REF):
        raise SpecError(
            f"reference to `{ref}`, which is not a local schema. The cloud "
            "spec is self-contained; a cross-file reference means the "
            "generator upstream changed."
        )
    return ref[len(SCHEMA_REF) :]


def component_at(ref: str, components: Dict[str, Any]) -> Any:
    if not ref.startswith(COMPONENT_REF):
        raise SpecError(
            f"reference to `{ref}`, which is not a local component. The cloud "
            "spec is self-contained; a cross-file reference means the "
            "generator upstream changed."
        )
    section, _, name = ref[len(COMPONENT_REF) :].partition("/")
    held = (components.get(section) or {}).get(name)
    if held is None:
        raise SpecError(
            f"reference to `{ref}`, which the spec does not declare"
        )
    return held


def relax_required(schemas: Dict[str, Any]) -> None:
    """Narrow a writable schema's required fields, in place.

    Applied to the loaded spec rather than to one renderer, so the types, the
    method signatures and the stateful handles cannot disagree about whether a
    field has to be there.
    """
    for name, kept in WRITABLE_SCHEMAS.items():
        schema = schemas.get(name)
        if schema is None:
            raise SpecError(
                f"WRITABLE_SCHEMAS names `{name}`, which the spec does not "
                "declare."
            )
        required = set(schema.get("required") or [])
        absent = sorted(kept - required)
        if absent:
            raise SpecError(
                f"WRITABLE_SCHEMAS keeps `{name}.{absent[0]}` required, which "
                "the spec no longer requires. Drop it from the entry."
            )
        schema["required"] = [f for f in schema["required"] if f in kept]


def split_union(schema: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], bool]:
    """Split a union into its concrete branches plus a nullability marker.

    Covers both spellings the cloud specs emit: `type: [X, "null"]` and
    `anyOf: [{...}, {type: "null"}]`.
    """
    schema_type = schema.get("type")
    if schema_type == "null":
        return [], True
    if isinstance(schema_type, list):
        concrete = [t for t in schema_type if t != "null"]
        rest = {k: v for k, v in schema.items() if k != "type"}
        return (
            [{**rest, "type": t} for t in concrete],
            len(concrete) != len(schema_type),
        )

    branches = schema.get("anyOf") or schema.get("oneOf")
    if not branches:
        return [schema], False

    concrete = [b for b in branches if b.get("type") != "null"]
    return concrete, len(concrete) != len(branches)


@dataclass(frozen=True)
class Route:
    resource: str
    path: str
    method: str
    operation: Dict[str, Any]
    shared: Dict[str, Any]

    @property
    def operation_id(self) -> str:
        return self.operation.get("operationId", "")

    @property
    def nodes(self) -> List[Any]:
        """Everything a schema walk must visit to cover this operation."""
        return [self.shared, self.operation]


def schema_nodes(routes: List[Route]) -> List[Any]:
    return [route.nodes for route in routes]


def generated_routes(
    resources: Dict[str, List[Route]],
) -> Dict[str, List[Route]]:
    """The routes the SDK generates, narrowed by resource and by operation."""
    declared = {
        route.operation_id for routes in resources.values() for route in routes
    }
    stale = sorted(set(EXCLUDED_OPERATIONS) - declared)
    if stale:
        raise SpecError(
            f"EXCLUDED_OPERATIONS names `{stale[0]}`, which the spec no longer "
            "declares. Drop the entry, add the renamed operation to EXCLUDED_OPERATIONS"
        )

    selected: Dict[str, List[Route]] = {}
    for resource, routes in resources.items():
        if GENERATED_RESOURCES and resource not in GENERATED_RESOURCES:
            continue
        wanted = GENERATED_OPERATIONS.get(resource)
        kept = [
            route
            for route in routes
            if route.operation_id not in EXCLUDED_OPERATIONS
            and (wanted is None or route.operation_id in wanted)
        ]
        if kept:
            selected[resource] = kept
    return selected


def operations_by_resource(spec: Dict[str, Any]) -> Dict[str, List[Route]]:
    """Group every operation under the tag that names its resource.

    The cloud generator tags each operation with the route folder it came
    from, and that folder is the SDK's directory for the resource, so the tag
    the resource name in both languages.
    """
    resources: Dict[str, List[Route]] = {}
    untagged: List[str] = []

    for route, item in (spec.get("paths") or {}).items():
        # Path-level parameters apply to every operation beneath them and can
        # hold the only reference to a schema, so they travel with each one.
        shared = {
            key: value for key, value in item.items() if key not in METHODS
        }
        for method, operation in item.items():
            if method not in METHODS:
                continue
            tags = operation.get("tags") or []
            if not tags:
                untagged.append(f"{method.upper()} {route}")
                continue
            for tag in tags:
                resources.setdefault(tag, []).append(
                    Route(
                        resource=tag,
                        path=route,
                        method=method,
                        operation=operation,
                        shared=shared,
                    )
                )

    if untagged:
        raise SpecError(
            "these operations carry no tag, so there is no resource to "
            "generate "
            "their shapes into:\n  " + "\n  ".join(sorted(untagged))
        )
    return resources


def schemas_reached(node: Any, components: Dict[str, Any]) -> Set[str]:
    """Every schema an operation can reach, transitively.

    Operations reference shared responses and parameters as well as schemas,
    so the walk follows a `$ref` into any component section and keeps going
    from whatever it lands on.
    """
    found: Set[str] = set()
    seen: Set[str] = set()

    def walk(current: Any) -> None:
        if isinstance(current, list):
            for value in current:
                walk(value)
            return
        if not isinstance(current, dict):
            return

        ref = current.get("$ref")
        if isinstance(ref, str) and ref not in seen:
            seen.add(ref)
            if ref.startswith(SCHEMA_REF):
                found.add(ref_name(ref))
            walk(component_at(ref, components))

        for value in current.values():
            walk(value)

    walk(node)
    return found


def schema_homes(
    resources: Dict[str, List[Route]], components: Dict[str, Any]
) -> Dict[str, str]:
    """Decide which module declares each schema.

    A shape one resource reaches belongs to that resource; one that several
    reach is declared once in `common` and imported, which is what keeps a
    shared type from being generated nine times.
    """
    users: Dict[str, List[str]] = {}
    for resource in sorted(resources):
        for name in sorted(
            schemas_reached(schema_nodes(resources[resource]), components)
        ):
            owners = users.setdefault(name, [])
            if resource not in owners:
                owners.append(resource)

    return {
        name: owners[0] if len(owners) == 1 else COMMON_RESOURCE
        for name, owners in users.items()
    }
