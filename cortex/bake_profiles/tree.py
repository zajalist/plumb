"""
cortex/bake_profiles/tree.py — the Tree profile (Task 11).

The Tree profile handles vegetation assets with seasonal state variants and
an attach-band region stub (for ornaments, lights, etc.).

Seasonal states map to PAP ``rest_states``; the profile's ``passes()`` injects
them into the PAP so downstream rendering knows which state meshes exist.

The attach-band region is a stub: a cylindrical band around the canopy where
attachments (e.g. Christmas lights) can be placed.  The full geometry of the
band is authored later; here we emit a placeholder dict that the conscience
renderer and the populate() loop can act on.

Canonical space: Z-up, right-handed, metres.
"""

from __future__ import annotations

from contracts import PAP, Semantics

# Seasonal state vocabulary.
SEASONAL_STATES: list[str] = ["summer", "autumn", "winter", "spring", "bare"]

# Default attach-band region stub.
_ATTACH_BAND_REGION: dict = {
    "id": "attach_band",
    "role": "attach",
    "description": "Cylindrical band around the canopy for seasonal attachments.",
    # Geometry: relative to the asset origin; full geometry is authored later.
    "origin": [0.0, 0.0, 0.0],  # will be set to canopy midpoint in passes()
    "radius": None,              # derived from geometry.aabb in passes()
    "height": None,              # derived from geometry.aabb in passes()
}


def detect(pap: PAP) -> bool:
    """True when ``pap.profile == 'tree'`` or semantics class is ``'tree'``."""
    if pap.profile == "tree":
        return True
    if pap.semantics and pap.semantics.cls == "tree":
        return True
    return False


def passes(pap: PAP) -> PAP:
    """Enrich a tree PAP with seasonal states and an attach-band region.

    Does not mutate ``pap``; returns a new PAP with ``rest_states`` set to the
    four seasonal variants and ``regions`` containing the attach-band stub.
    The attach-band geometry is derived from the PAP's geometry AABB.
    """
    # Derive attach-band geometry from the PAP's AABB.
    half = pap.geometry.aabb or pap.geometry.obb or [0.5, 0.5, 1.0]
    radius = float(max(half[0], half[1]))
    height_full = float(half[2]) * 2.0  # full height
    canopy_z = height_full * 0.6        # attach at 60% up (canopy midpoint)

    attach_region = dict(_ATTACH_BAND_REGION)
    attach_region["origin"] = [0.0, 0.0, canopy_z]
    attach_region["radius"] = radius
    attach_region["height"] = height_full * 0.3  # 30% of tree height

    # Merge with any existing regions (don't duplicate if already present).
    existing_regions = list(pap.regions)
    region_ids = {r.get("id") for r in existing_regions}
    if "attach_band" not in region_ids:
        existing_regions.append(attach_region)

    # Build updated PAP.
    updated = pap.model_copy(
        update={
            "rest_states": list(SEASONAL_STATES),
            "regions": existing_regions,
        }
    )
    return updated


# Profile constants (consumed by __init__.py).
DEFAULT_STATES: list[str] = SEASONAL_STATES
DEFAULT_REGIONS: list[dict] = [dict(_ATTACH_BAND_REGION)]
DEFAULT_CONSTRAINTS: list[dict] = []
