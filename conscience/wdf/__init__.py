"""
conscience.wdf — the `.wdf` world language (Task B3, spec §12.2).

A portable, diffable, validatable text language: a `vocabulary` of typed assets
plus a `scene` of placements, laws and environment fields. `dumps` renders the
in-memory `WdfDocument` to the §12.2 surface syntax; `loads` parses it back. The
proof that it is a real language is the round-trip identity `loads(dumps(doc)) == doc`.

`.wdf` is the human-facing language; the verdict (contracts.py) is what the gates
emit. This package never imports cortex internals.
"""

from .model import (
    Asset,
    Field,
    Joint,
    Law,
    Placement,
    Scene,
    Vocabulary,
    WdfDocument,
)
from .parse import WdfParseError, loads
from .serialize import dumps

__all__ = [
    "Asset",
    "Field",
    "Joint",
    "Law",
    "Placement",
    "Scene",
    "Vocabulary",
    "WdfDocument",
    "WdfParseError",
    "dumps",
    "loads",
]
