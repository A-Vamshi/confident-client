"""Folding hand-written code into generated files, after rendering.

The generator says what the spec says. A few things a client needs are not in
the spec at all — prompt caching and background refresh is the first of them —
and belong on a generated class anyway. Each such edit is declared beside the
resource it belongs to and applied here.

Overlays are applied to the rendered text before anything is written, so
`--check`, the idempotence guarantee and both formatters cover overlaid code
exactly as they cover generated code. Every anchor must match the number of
times it says: a generator change that moves one fails the run rather than
quietly dropping the feature.
"""

from pathlib import Path
from typing import Dict, List, Tuple

from ..constants import REPO_ROOT
from ..errors import SpecError
from ..generate_files import format_python, format_typescript
from .overlay import Overlay
from .prompts import prompts_overlay, ts_prompts_overlay


def overlays(descriptive: bool) -> List[Overlay]:
    return [prompts_overlay(descriptive), ts_prompts_overlay(descriptive)]


# ===== Applying them =====


def run_after_generation(
    outputs: List[Tuple[Path, str]], descriptive: bool = True
) -> List[Tuple[Path, str]]:
    """Fold every overlay into the files it names, before any are written."""
    pending: Dict[str, Overlay] = {
        overlay.path: overlay for overlay in overlays(descriptive)
    }

    applied: List[Tuple[Path, str]] = []
    for path, content in outputs:
        overlay = pending.pop(str(path.relative_to(REPO_ROOT)), None)
        if overlay is None:
            applied.append((path, content))
            continue
        name = str(path.relative_to(REPO_ROOT))
        overlaid = overlay.apply(content)
        # Both formatters have already run, so an overlaid file goes back
        # through its own to land on the same house style as everything else.
        if path.suffix == ".py":
            overlaid = format_python(overlaid)
        else:
            overlaid = format_typescript({name: overlaid})[name]
        applied.append((path, overlaid))

    if pending:
        raise SpecError(
            "these overlays name a file the generator does not produce: "
            + ", ".join(sorted(pending))
            + ". Update sdkgen/custom_overlays/, or the resource it overlays."
        )
    return applied
