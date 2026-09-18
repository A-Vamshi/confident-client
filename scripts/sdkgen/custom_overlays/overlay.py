"""What one overlay is: a set of exact edits against one rendered file.

Kept apart from both the pass that applies overlays and the overlays
themselves, so neither has to import the other.
"""

from dataclasses import dataclass, field
from typing import Tuple

from ..errors import SpecError


@dataclass(frozen=True)
class Edit:
    """One exact replacement, and how many times it must match."""

    anchor: str
    replacement: str
    occurrences: int = 1


@dataclass(frozen=True)
class Overlay:
    """The edits one generated file takes after it is rendered."""

    path: str
    edits: Tuple[Edit, ...] = field(default_factory=tuple)

    def apply(self, text: str) -> str:
        for edit in self.edits:
            found = text.count(edit.anchor)
            if found != edit.occurrences:
                raise SpecError(
                    f"the overlay for {self.path} expected "
                    f"{edit.occurrences} occurrence(s) of\n\n"
                    f"{edit.anchor}\n\n"
                    f"but the generated file has {found}. The generator's "
                    "output moved; update the overlay in "
                    "the overlay in sdkgen/custom_overlays/ to match it."
                )
            text = text.replace(edit.anchor, edit.replacement)
        return text
