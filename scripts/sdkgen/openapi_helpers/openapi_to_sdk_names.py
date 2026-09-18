"""How a name in the spec becomes a name in the SDK.

Pure string work: no schema is read here and nothing is written. The rules are
shared by both languages, which is what keeps a Python attribute and its
TypeScript property derived from the same spelling.
"""

import re

from typing import Iterable, List, Set

from ..constants import (
    API_VERSION_SEGMENT,
    PATH_PARAMETER,
    RESOURCE_MODULES,
    SIBILANTS,
    UPPERCASE_RUN,
    WORD,
)


def snake_case(name: str) -> str:
    # Split on acronym boundaries too, so `listAIConnections` reads as
    # `list_ai_connections` rather than `list_a_i_connections`.
    return "_".join(word.lower() for word in WORD.findall(name))


def camel_case(name: str) -> str:
    parts = WORD.findall(name)
    if not parts:
        return name
    return parts[0].lower() + "".join(part.title() for part in parts[1:])


def pascal_case(name: str) -> str:
    parts = re.split(r"[^A-Za-z0-9]+", name)
    return "".join(part[:1].upper() + part[1:] for part in parts if part)


def singular(name: str) -> str:
    if name.endswith("ies"):
        return f"{name[:-3]}y"
    # A noun ending in a sibilant takes -es, so the stem keeps its last letter:
    # `branches` is `branch`, not `branche`.
    if name.endswith("es") and name[:-2].endswith(SIBILANTS):
        return name[:-2]
    if name.endswith("s") and not name.endswith("ss"):
        return name[:-1]
    return name


def enum_member_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", str(value)).upper().strip("_")


def acronyms_in(names: Iterable[str]) -> Set[str]:
    """The acronyms the spec's own type names use.

    Read off the schema names rather than hardcoded, so a client class agrees
    with the types it returns instead of the two drifting.
    """
    found: Set[str] = set()
    for name in names:
        for match in UPPERCASE_RUN.finditer(name):
            run = match.group()
            end = match.end()
            if end < len(name) and name[end].islower():
                run = run[:-1]
            if len(run) >= 2:
                found.add(run)
    return found


def client_class_name(
    resource: str, acronyms: Set[str], suffix: str = "Client"
) -> str:
    parts = []
    for token in re.split(r"[^A-Za-z0-9]+", resource):
        if not token:
            continue
        parts.append(
            token.upper()
            if token.upper() in acronyms
            else token[:1].upper() + token[1:]
        )
    return "".join(parts) + suffix


def python_module_for(resource: str) -> str:
    module = RESOURCE_MODULES.get(resource, resource).replace("-", "_")
    return f"confidentai.{module}.types"


def ts_module_for(resource: str) -> str:
    """The directory a resource's TypeScript lives in, kebab-cased like its
    tag."""
    return RESOURCE_MODULES.get(resource, resource)


def method_name(operation_id: str, resource: str) -> str:
    """The method one operation is exposed as, minus its resource's own name.

    A method already sits on its resource's client, so repeating the resource
    in the name says it twice: `client.projects.list_projects()`. The tag is
    deleted from the operation id wherever it appears, in whichever number the
    spec wrote it.

    Only at index 1 or later, and never when it is the whole name: the verb
    has to survive, or `evaluateTrace` on tag `evaluate` would become
    `trace()`.
    """
    parts = [token.lower() for token in WORD.findall(operation_id)]
    tag = [token.lower() for token in WORD.findall(resource)]
    spellings = (
        tag,
        tag[:-1] + [singular(tag[-1])],
        [singular(token) for token in tag],
    )
    for spelling in spellings:
        width = len(spelling)
        if len(parts) <= width:
            continue
        for start in range(1, len(parts) - width + 1):
            if parts[start : start + width] == spelling:
                return "_".join(parts[:start] + parts[start + width :])
    return "_".join(parts)


def endpoint_member(path: str) -> str:
    """The enum member naming one route.

    A parameter segment names nothing of its own; it marks the literal before
    it as one of many, so that literal is singularized. The name is a function
    of this path alone, so adding a route can never rename another's member.
    """
    tokens: List[str] = []
    for segment in path.strip("/").split("/"):
        if API_VERSION_SEGMENT.fullmatch(segment):
            continue
        if segment.startswith("{"):
            if tokens:
                tokens[-1] = singular(tokens[-1])
            continue
        tokens.extend(part for part in segment.split("-") if part)
    return "_".join(token.upper() for token in tokens) + "_ENDPOINT"


def endpoint_value(path: str) -> str:
    return PATH_PARAMETER.sub(r":\1", path)
