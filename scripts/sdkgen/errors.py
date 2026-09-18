"""The one error the generator raises.

Every stop is the spec saying something the SDK cannot express, so there is
one exception and its message names the schema or operation at fault.
"""


class SpecError(Exception):
    """The spec cannot be generated from, and needs fixing."""
