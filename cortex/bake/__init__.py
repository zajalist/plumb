"""
cortex/bake/ — the asset bake pipeline.

  geometry.py  (Task 2) — load mesh -> AABB/OBB, volume, watertight, convex parts.
  physical.py  (Task 3) — composition-aware mass / CoM / inertia.
  __init__:bake_asset    (Task 3) — composes geometry + physical into a full PAP.

Geometry is the first stage and the only one Task 2 owns; the convex parts it
produces are consumed by the physical bake and the collision gate.
"""

from __future__ import annotations

from contracts import PAP, Provenance
from cortex.bake.geometry import bake_geometry_parts
from cortex.bake.physical import bake_physical

__all__ = ["bake_asset"]


def bake_asset(
    asset_id: str,
    mesh_path: str,
    part_materials: dict | None = None,
    profile: str = "rigid_prop",
) -> PAP:
    """Bake a full :class:`PAP` for an asset: geometry (T2) + physical (T3).

    Loads and decomposes the mesh once via :func:`bake_geometry_parts`, then feeds
    the same convex parts into :func:`bake_physical` so geometry and physics agree on
    the decomposition. ``part_materials`` maps a part index/key → material name; any
    fields fed from those authored materials are recorded in ``provenance.locked`` so
    a later human/agent never silently overwrites a confirmed choice. With no authored
    materials every part is ``"default"`` and nothing is locked (a pure auto-bake).
    """
    geometry, parts, _decomposition_flag = bake_geometry_parts(mesh_path)

    materials = part_materials or {}
    physical = bake_physical(parts, materials)

    locked: list[str] = []
    if materials:
        # Authored materials drove mass / CoM / inertia, so those physical fields
        # are human-anchored, not free to re-guess.
        locked = [
            "physical.mass_kg",
            "physical.com",
            "physical.inertia",
            "semantics.materials",
        ]

    return PAP(
        asset_id=asset_id,
        profile=profile,
        geometry=geometry,
        physical=physical,
        provenance=Provenance(auto=not materials, edited_fields=[], locked=locked),
    )
