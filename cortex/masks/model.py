"""
cortex/masks/model.py — the Mask data model (design spec §3).

A Mask is one semantic overlay on a baked asset. Every mask is one of four render
*archetypes* and comes from one of four *sources*; the studio renders it and the rail
lists it. Masks bind to the asset's convex parts (ids like ``part_00``) which carry
centroid/extent/verts/tris — so any source (geometry, HF, Gemini, agent-over-MCP) can
produce one and the renderer treats them uniformly.

Shapes are intentionally plain dicts inside ``data`` so the same model round-trips through
the on-disk store, the HTTP API, and the FastMCP tools without bespoke (de)serialisers.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, model_validator

Archetype = Literal["categorical", "scalar", "vector", "markers"]
Source = Literal["geometry", "hf", "gemini", "mcp"]
Category = Literal["material", "physics", "artistic", "affordance", "custom"]
Role = Literal["surface", "overlay"]


def role_for(archetype: str) -> Role:
    """Surface masks recolour the mesh (mutually exclusive); overlays stack on top."""
    return "surface" if archetype in ("categorical", "scalar") else "overlay"


def _validate_data(archetype: str, data: dict) -> None:
    """Raise ``ValueError`` if ``data`` doesn't match its archetype's shape."""
    if not isinstance(data, dict):
        raise ValueError("mask data must be a dict")
    if archetype == "categorical":
        regions = data.get("regions")
        if not isinstance(regions, list) or not regions:
            raise ValueError("categorical mask needs a non-empty 'regions' list")
        for r in regions:
            if not isinstance(r, dict) or "label" not in r or "color" not in r:
                raise ValueError("each region needs 'label' and 'color'")
    elif archetype == "scalar":
        per_part = data.get("per_part")
        if not isinstance(per_part, dict) or not per_part:
            raise ValueError("scalar mask needs a non-empty 'per_part' map")
        rng = data.get("range")
        if not (isinstance(rng, (list, tuple)) and len(rng) == 2):
            raise ValueError("scalar mask needs 'range': [lo, hi]")
    elif archetype == "vector":
        if "samples" not in data and "field" not in data:
            raise ValueError("vector mask needs 'samples' or 'field'")
    elif archetype == "markers":
        if not any(k in data for k in ("points", "lines", "axes")):
            raise ValueError("markers mask needs at least one of points/lines/axes")


def derive_legend(archetype: str, data: dict) -> dict:
    """Legend the rail/canvas renders: category swatches or a value ramp."""
    if archetype == "categorical":
        items = [{"label": r.get("label", ""), "color": r.get("color", "#888")}
                 for r in data.get("regions", [])]
        return {"kind": "swatches", "items": items}
    if archetype == "scalar":
        return {"kind": "ramp", "range": list(data.get("range", [0, 1])),
                "ramp": data.get("ramp", "plasma")}
    return {"kind": "none"}


class Mask(BaseModel):
    id: str
    asset_id: str
    name: str
    source: Source
    category: Category
    archetype: Archetype
    role: Role = "surface"
    data: dict[str, Any] = {}
    legend: dict[str, Any] = {}
    confidence: Optional[float] = None
    provider_key: str = ""
    version: int = 1

    @model_validator(mode="after")
    def _fill(self) -> "Mask":
        self.role = role_for(self.archetype)
        _validate_data(self.archetype, self.data)
        if not self.legend:
            self.legend = derive_legend(self.archetype, self.data)
        return self
