"""
Custom (MCP-authored) masks — the agent source.

These have no ``compute``: Claude (or any MCP client) *authors* the mask directly through
the cortex ``add_mask`` tool, which calls :func:`ingest`. The mask is validated by the same
``Mask`` model and lands in the same store, so it renders in the UI identically to a
computed one. No registry entry needed — authored masks show up via ``GET /masks``.
"""

from __future__ import annotations

import re

from .. import store
from ..model import Mask


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.strip().lower()).strip("_") or "mask"


def ingest(asset_id: str, name: str, archetype: str, data: dict,
           category: str = "custom", mask_id: str | None = None,
           confidence: float | None = None) -> Mask:
    """Validate an authored mask and persist it. source is always ``mcp``."""
    mask = Mask(
        id=mask_id or _slug(name), asset_id=asset_id, name=name, source="mcp",
        category=category, archetype=archetype, data=data, confidence=confidence,
        provider_key="custom",
    )
    return store.upsert(mask)


def seed_grasp_points(asset_id: str, points: list[list[float]]) -> Mask:
    """Example MCP mask used in the demo/tests: labelled grasp points."""
    data = {"points": [{"pos": list(p), "label": "grip", "kind": "grasp"} for p in points]}
    return ingest(asset_id, "Grasp points", "markers", data, category="custom",
                  mask_id="grasp_points")
