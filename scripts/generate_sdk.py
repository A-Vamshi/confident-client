"""Generate the SDKs from the OpenAPI spec confident-cloud publishes.

The entrypoint, and the only file here you run. It reads the spec once, hands
it to each renderer in turn, then classifies every output before writing any
of it, so a run that refuses to overwrite a hand-written file leaves the tree
as it found it.

    poetry run python ../scripts/generate_sdk.py            # write
    poetry run python ../scripts/generate_sdk.py --check    # verify (CI)
"""

import argparse
import os
import sys

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

import yaml

from sdkgen.clients import (
    render_endpoints,
    render_generated_clients,
    render_typescript_endpoints,
    render_typescript_generated_clients,
    resource_client_files,
    ts_resource_client_files,
)
from sdkgen.constants import (
    CANONICAL_SPEC_LOCATION,
    CLIENTS_PACKAGE,
    REPO_ROOT,
    COMMON_RESOURCE,
    DEFAULT_SPEC_DIR,
    MERGED_SPEC,
)
from sdkgen.core.errors import SpecError
from sdkgen.core.naming import acronyms_in
from sdkgen.core.output import (
    ResourcePaths,
    banner,
    format_python,
    format_typescript,
    is_generated,
)
from sdkgen.core.spec import (
    generated_routes,
    operations_by_resource,
    relax_required,
    schema_homes,
    schema_nodes,
    schemas_reached,
)
from sdkgen.overlays import run_after_generation
from sdkgen.types import (
    declare,
    render_python,
    render_typescript,
    sort_by_dependency,
)
from sdkgen.stateful_clients import (
    handle_module,
    load_stateful_resources,
    render_handle,
    render_stateful_clients,
    render_ts_handle,
    render_ts_stateful_clients,
    ts_handle_module,
)

Outputs = List[Tuple[Path, str]]


# ===== Reading the spec =====


def load_schemas(spec_dir: Path) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """The merged spec and its component schemas, ready to read."""
    spec_path = spec_dir / MERGED_SPEC
    if not spec_path.exists():
        raise SystemExit(
            f"no {MERGED_SPEC} in {spec_dir}. Point --spec-dir or "
            "OPENAPI_SPEC_DIR at confident-cloud's packages/shared/openapi."
        )

    spec = yaml.safe_load(spec_path.read_text())
    components = spec.get("components") or {}
    relax_required(components.get("schemas") or {})
    return spec, components


def resource_source(resource: str) -> str:
    """What a generated file's banner cites as where it came from."""
    if resource == COMMON_RESOURCE:
        return (
            f"the shapes shared across {CANONICAL_SPEC_LOCATION}/{MERGED_SPEC}"
        )
    return f"{CANONICAL_SPEC_LOCATION}/{MERGED_SPEC} (tag: {resource})"


# ===== One file, with its banner on top =====


def python_file(source: str, body: str) -> str:
    return format_python(
        "\n".join(banner("#", source) + body.split("\n")) + "\n"
    )


def typescript_file(source: str, body: str) -> str:
    return "\n".join(banner("//", source) + body.split("\n")) + "\n"


# ===== The three rounds of rendering =====


def render_wire_types(home: Dict[str, str], schemas: Dict[str, Any]) -> Outputs:
    """One types module per resource, plus `common` for what they share."""
    owned: Dict[str, Dict[str, Any]] = {}
    for name in sorted(home):
        owned.setdefault(home[name], {})[name] = schemas[name]

    outputs: Outputs = []
    for resource in sorted(owned):
        source = resource_source(resource)
        try:
            module = declare(resource, owned[resource], home)
            sort_by_dependency(module)
        except SpecError as error:
            label = (
                f"{COMMON_RESOURCE} (shapes several resources share)"
                if resource == COMMON_RESOURCE
                else f"tag {resource}"
            )
            raise SpecError(f"{label}: {error}") from None

        paths = ResourcePaths(name=resource)
        outputs.append((paths.python_path, render_python(module, source)))
        outputs.append(
            (paths.typescript_path, render_typescript(module, source))
        )
    return outputs


def render_per_resource(
    generating: Dict[str, Any],
    home: Dict[str, str],
    acronyms: Set[str],
    schemas: Dict[str, Any],
    stateful: Dict[str, Any],
    descriptive: bool,
) -> Outputs:
    """Every operations module and client a resource generates, plus its
    stateful handle when stateful_resources.yml declares one."""
    outputs: Outputs = []
    for resource in sorted(generating):
        paths = ResourcePaths(name=resource)
        source = resource_source(resource)
        rounds = (
            (resource_client_files, paths.python_path, python_file),
            (ts_resource_client_files, paths.typescript_path, typescript_file),
        )
        for render, path, wrap in rounds:
            for filename, body in render(
                resource,
                generating[resource],
                home,
                acronyms,
                schemas,
                descriptive,
            ):
                outputs.append((path.parent / filename, wrap(source, body)))

        if resource not in stateful:
            continue
        handle = (
            resource,
            stateful[resource],
            generating[resource],
            home,
            acronyms,
            schemas,
            descriptive,
        )
        outputs.append(
            (
                paths.python_path.parent / handle_module(stateful[resource]),
                python_file(source, render_handle(*handle)),
            )
        )
        outputs.append(
            (
                paths.typescript_path.parent
                / ts_handle_module(stateful[resource]),
                typescript_file(source, render_ts_handle(*handle)),
            )
        )
    return outputs


def render_shared(
    generating: Dict[str, Any],
    acronyms: Set[str],
    stateful: Dict[str, Any],
    descriptive: bool,
) -> Outputs:
    """The files no single resource owns: the endpoint enum, and the mixins
    that hang every client off ConfidentAI."""
    source = f"the routes in {CANONICAL_SPEC_LOCATION}/{MERGED_SPEC}"
    clients = REPO_ROOT / "python" / "confidentai" / CLIENTS_PACKAGE
    ts_clients = REPO_ROOT / "typescript" / "src" / CLIENTS_PACKAGE

    outputs: Outputs = [
        (
            clients / "generated.py",
            python_file(source, render_generated_clients(generating, acronyms)),
        ),
        (
            ts_clients / "generated.ts",
            typescript_file(
                source,
                render_typescript_generated_clients(generating, acronyms),
            ),
        ),
    ]
    if any(resource in stateful for resource in generating):
        outputs.append(
            (
                clients / "stateful.py",
                python_file(
                    source, render_stateful_clients(stateful, list(generating))
                ),
            )
        )
        outputs.append(
            (
                ts_clients / "stateful.ts",
                typescript_file(
                    source,
                    render_ts_stateful_clients(stateful, list(generating)),
                ),
            )
        )

    outputs.append(
        (
            REPO_ROOT / "python" / "confidentai" / "endpoints.py",
            render_endpoints(generating, source, descriptive),
        )
    )
    outputs.append(
        (
            REPO_ROOT / "typescript" / "src" / "endpoints.ts",
            typescript_file(
                source, render_typescript_endpoints(generating, descriptive)
            ),
        )
    )
    return outputs


# ===== One run =====


@dataclass
class Generated:
    """What one run writes, and what it deliberately left out."""

    outputs: Outputs = field(default_factory=list)
    unreachable_schemas: List[str] = field(default_factory=list)
    skipped_resources: List[str] = field(default_factory=list)


def build(spec_dir: Path, descriptive: bool = True) -> Generated:
    spec, components = load_schemas(spec_dir)
    schemas = components.get("schemas") or {}

    tagged = operations_by_resource(spec)
    if COMMON_RESOURCE in tagged:
        raise SpecError(
            f"the spec tags operations with `{COMMON_RESOURCE}`, which "
            "collides with the module this script generates for shapes "
            "several resources share. Rename the route folder upstream."
        )

    generating = generated_routes(tagged)
    home = schema_homes(generating, components)
    acronyms = acronyms_in(schemas)
    stateful = load_stateful_resources()

    outputs = (
        render_wire_types(home, schemas)
        + render_per_resource(
            generating, home, acronyms, schemas, stateful, descriptive
        )
        + render_shared(generating, acronyms, stateful, descriptive)
    )

    # Prettier runs once over every TypeScript file rather than per file, so
    # one node startup covers the whole tree.
    rendered = {
        str(path.relative_to(REPO_ROOT)): content
        for path, content in outputs
        if path.suffix == ".ts"
    }
    formatted = format_typescript(rendered)
    outputs = [
        (path, formatted.get(str(path.relative_to(REPO_ROOT)), content))
        for path, content in outputs
    ]

    # Overlaid last, over formatted text: the anchors an overlay matches are
    # then the lines a reader sees in the committed file.
    outputs = run_after_generation(outputs, descriptive)

    # Measured against every tag, skipped ones included, so a resource waiting
    # to be generated does not read as drift in the spec.
    reached: Set[str] = set()
    for routes in tagged.values():
        reached |= schemas_reached(schema_nodes(routes), components)

    return Generated(
        outputs=outputs,
        unreachable_schemas=sorted(set(schemas) - reached),
        skipped_resources=sorted(set(tagged) - set(generating)),
    )


# ===== The command line =====


def report(generated: Generated) -> None:
    """What the run left out, which is never an error but is worth saying."""
    if generated.skipped_resources:
        skipped = generated.skipped_resources
        shown = ", ".join(skipped[:6])
        if len(skipped) > 6:
            shown += f", and {len(skipped) - 6} more"
        print(
            f"skipping {len(skipped)} resources outside "
            f"GENERATED_RESOURCES: {shown}"
        )

    if generated.unreachable_schemas:
        print(
            f"{len(generated.unreachable_schemas)} schemas are declared but "
            "no operation reaches them, so they are not generated:"
        )
        for name in generated.unreachable_schemas:
            print(f"  {name}")


def classify(outputs: Outputs) -> Tuple[List[Path], Outputs]:
    """Split the run into what is hand-written and what is safe to write.

    Every file is classified before any is written, so a run that refuses to
    overwrite a hand-written file leaves the tree as it found it rather than
    half-regenerated.
    """
    handwritten: List[Path] = []
    changed: Outputs = []
    for path, content in outputs:
        current = path.read_text() if path.exists() else None
        if current == content:
            continue
        if current is not None and not is_generated(current):
            handwritten.append(path.relative_to(REPO_ROOT))
            continue
        changed.append((path, content))
    return handwritten, changed


def as_boolean(value: str) -> bool:
    if value.lower() in ("true", "false"):
        return value.lower() == "true"
    raise argparse.ArgumentTypeError(f"expected true or false, got {value!r}")


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero if any generated file is missing or stale",
    )
    parser.add_argument(
        "--spec-dir",
        type=Path,
        default=Path(os.environ.get("OPENAPI_SPEC_DIR", DEFAULT_SPEC_DIR)),
        help=f"the directory holding confident-cloud's {MERGED_SPEC}",
    )
    parser.add_argument(
        "--descriptive",
        type=as_boolean,
        default=True,
        metavar="true|false",
        help="keep docstrings, JSDoc and explanatory comments in the output",
    )
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()

    try:
        generated = build(
            arguments.spec_dir.resolve(), descriptive=arguments.descriptive
        )
    except SpecError as error:
        print(error, file=sys.stderr)
        return 2

    report(generated)
    handwritten, changed = classify(generated.outputs)

    if handwritten:
        print(
            "these files are hand-written, and the files generated for their "
            "resource would overwrite them:",
            file=sys.stderr,
        )
        for path in handwritten:
            print(f"  {path}", file=sys.stderr)
        print(
            "\nMove what they declare into the hand-written layer, or drop "
            "the resource from GENERATED_RESOURCES in sdkgen/constants.py, "
            "then run again.",
            file=sys.stderr,
        )
        return 2

    if arguments.check:
        if changed:
            print("Generated files are stale:", file=sys.stderr)
            for path, _ in changed:
                print(f"  {path.relative_to(REPO_ROOT)}", file=sys.stderr)
            print(
                "\nRun `poetry run python ../scripts/generate_sdk.py` from "
                "python/ and commit the result.",
                file=sys.stderr,
            )
            return 1
        print(
            f"Generated files are up to date ({len(generated.outputs)} files)."
        )
        return 0

    for path, content in changed:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        print(f"wrote {path.relative_to(REPO_ROOT)}")
    if not changed:
        print("no changes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
