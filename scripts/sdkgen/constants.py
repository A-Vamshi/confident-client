"""Everything the generator is told, as data.

No logic lives here: an entry is a name, a path, or a set of them. A rule that
needs a condition belongs in code, not in this file.

The sections separate what you may edit — which routes are generated, and the
few shapes the spec cannot describe on its own — from what is a fact about the
spec or about Python and TypeScript, where a change breaks the output.
"""

import re

from pathlib import Path
from typing import Dict, FrozenSet


# ===== Where the spec is read from, and the SDK written to =====

REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_SPEC_DIR = (
    REPO_ROOT.parent / "confident-cloud" / "packages" / "shared" / "openapi"
)

MERGED_SPEC = "openapi.yml"

# Headers cite this rather than wherever the specs were read from, so output
# does not change when CI points --spec-dir at a checkout of confident-cloud.
CANONICAL_SPEC_LOCATION = "packages/shared/openapi"

DEFAULT_OUT_ROOT = REPO_ROOT

# The stateful handles, described in YAML beside this file rather than here:
# they are the one part of the generator a reader is expected to hand-edit.
STATEFUL_RESOURCES = (
    Path(__file__).resolve().parents[1] / "stateful_resources.yml"
)


# ===== Which routes are generated =====

# The tags the SDK generates. A resource outside this set is ignored entirely:
# a shape only it reaches is not generated, and a shape it shares with a
# generated resource is owned as if the tag were absent from the spec. Empty
# means every tag in the spec.
GENERATED_RESOURCES: FrozenSet[str] = frozenset()

# A resource listed here generates only these operations. One absent from it
# generates all of them.
GENERATED_OPERATIONS: Dict[str, FrozenSet[str]] = {}

# Operations we ignore instead of generating. Naming one the spec no longer
# declares stops the generator, so a rename upstream cannot slip past.
EXCLUDED_OPERATIONS = frozenset(
    {
        # The `download` pair answers 302 with a `Location` banner and no body,
        # so there is no response schema to validate into.
        "downloadOrganizationAuditLogExport",
        "downloadProjectAuditLogExport",
    }
)

# A resource that must generate into a module other than its tag. The name is
# kebab-cased like a tag, so it snake_cases for Python and is used as-is for
# TypeScript.
RESOURCE_MODULES: Dict[str, str] = {}


# ===== What the spec cannot say, and this file must =====

# The resources served by the organization API key. Everything else uses the
# project key. The spec declares one scheme for all of them, so the split
# cannot be read from it.
ORGANIZATION_KEY_RESOURCES = frozenset({"organization", "projects"})

# A union body has no one set of fields to flatten into arguments, so the whole
# body becomes a single parameter. This names that parameter, per schema. A
# union body with no entry here stops the generator.
UNION_BODY_PARAMETERS = {
    "AddQueueItemsRequest": "items",
    "CreateAnnotationRequest": "annotation",
    "CreateGovernanceControlVersionRequest": "control_config",
    "GoldenRequest": "golden",
    "PushPromptRequest": "prompt",
    "UpdateProjectModelRequest": "model_config",
}

# Response shapes a caller must also be able to write down, and the only fields
# that stay required when they do. A stateful handle holds these before the API
# has seen them — a golden just added to a pulled dataset has no id and none of
# the fields the server fills in — so requiring what a response always carries
# would make the value impossible to construct. Naming what stays rather than
# what goes means a field added upstream is relaxed with the rest.
#
# Every name here must be a field the spec requires, or the generator stops, so
# a stale entry cannot sit unnoticed.
WRITABLE_SCHEMAS: Dict[str, FrozenSet[str]] = {
    "SingleTurnGolden": frozenset({"input"}),
    "MultiTurnGolden": frozenset({"scenario"}),
}


# ===== Names the generated tree is built from =====

# The entrypoint named in every generated banner. A literal rather than
# __file__, so splitting or renaming a module cannot change the output.
SCRIPT_PATH = Path("scripts/generate_sdk.py")

# The token that marks a file as this generator's to overwrite. A file without
# it is treated as hand-written and the run refuses rather than clobbering it.
GENERATED_MARKER = "@generated"

# Everywhere else a resource is a tag in the spec — which is the route folder
# in confident-cloud, and the SDK directory generated from it. This is the one
# exception: the module holding shapes several resources reach, which no tag
# owns. The generator stops if the spec ever declares a tag by this name.
COMMON_RESOURCE = "common"

# The single enum every route is named in.
ENDPOINTS_CLASS = "Endpoints"

# The file holding one URL group's operations, one method pair per operation
# the spec declares. "operations" rather than "methods" because `method` is
# already the HTTP verb here — see METHOD_ORDER and HttpMethods.
OPERATIONS_MODULE = "operations.py"
TS_OPERATIONS_MODULE = "operations.ts"

# The package holding the mixins that hang every client off ConfidentAI.
CLIENTS_PACKAGE = "clients"

# Where a handle's hand-written methods come from. Named in the YAML by
# function, so one module serves every resource.
HELPERS_MODULE = "confidentai.utils.helpers"


# ===== How the spec is spelled =====

SCHEMA_REF = "#/components/schemas/"
COMPONENT_REF = "#/components/"

# Every verb a path item may carry, and the order routes are rendered in.
METHODS = frozenset(
    {"get", "post", "put", "patch", "delete", "head", "options", "trace"}
)
METHOD_ORDER = ("get", "post", "put", "patch", "delete")

PATH_PARAMETER = re.compile(r"\{(\w+)\}")
API_VERSION_SEGMENT = re.compile(r"v\d+")


# ===== How a name is taken apart =====

# One word of an identifier, acronym-aware: `listAIConnections` splits into
# list, AI, connections rather than list, a, i, connections.
WORD = re.compile(r"[A-Z]+(?![a-z])|[A-Z][a-z0-9]*|[a-z0-9]+")

# A run of capitals in a component name, which is how the acronyms the spec
# uses are discovered rather than listed here.
UPPERCASE_RUN = re.compile(r"[A-Z]{2,}")

# Endings that take `-es` in the plural, so singularizing keeps the stem whole.
SIBILANTS = ("s", "sh", "ch", "x", "z")


# ===== Facts about Python and TypeScript =====

# The spec's scalar types, as each language spells them.
PRIMITIVES = {
    "string": ("str", "string"),
    "integer": ("int", "number"),
    "number": ("float", "number"),
    "boolean": ("bool", "boolean"),
}

# pydantic resolves these on the class itself, so a field that snake_cases onto
# one of them shadows the framework and raises at class-definition time.
PYDANTIC_RESERVED = {
    "model_config",
    "model_fields",
    "model_computed_fields",
    "model_extra",
    "model_fields_set",
}

TS_IDENTIFIER = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")

# A class body is always strict mode, where these cannot name a parameter.
# Python accepts every one of them, so only TypeScript escapes.
TS_RESERVED = frozenset(
    {
        "arguments",
        "await",
        "break",
        "case",
        "catch",
        "class",
        "const",
        "continue",
        "debugger",
        "default",
        "delete",
        "do",
        "else",
        "enum",
        "eval",
        "export",
        "extends",
        "false",
        "finally",
        "for",
        "function",
        "if",
        "implements",
        "import",
        "in",
        "instanceof",
        "interface",
        "let",
        "new",
        "null",
        "package",
        "private",
        "protected",
        "public",
        "return",
        "static",
        "super",
        "switch",
        "this",
        "throw",
        "true",
        "try",
        "typeof",
        "var",
        "void",
        "while",
        "with",
        "yield",
    }
)


# ===== How the output is formatted =====

# Black owns Python's line breaking; the width is repeated here because
# docstrings are wrapped before black ever sees them.
PYTHON_LINE_LENGTH = 80

# Prettier owns TypeScript's, and is run from the SDK's own node_modules.
TYPESCRIPT_ROOT = REPO_ROOT / "typescript"
PRETTIER_CONFIG = REPO_ROOT / "typescript" / ".prettierrc"
