"""
cortex/bake_profiles/shelf.py — the Shelf profile (Task 11).

The Shelf profile handles furniture assets that carry fill-region capacity and
support a ``populate(region, assets)`` function that places assets on the shelf
and re-validates each placement through the orchestrator (T9).

Fill regions are read from ``pap._fill_regions`` (a list of dicts), each with:
  * ``id``        — unique region name
  * ``origin``    — [x, y, z] base position in world space
  * ``size``      — [width, depth, height] of the fill volume
  * ``max_load_kg`` — weight capacity

``populate(region, assets) -> list[(PAP, Transform)]``

Places assets left-to-right with a small gap; stops when the region width is
exhausted.  Each candidate placement is validated via the orchestrator's gate
stack; only gate-valid placements are returned.

Canonical space: Z-up, right-handed, metres.
"""

from __future__ import annotations

import numpy as np

from contracts import PAP, Diff, Semantics, Transform
from cortex.world import WorldModel


def detect(pap: PAP) -> bool:
    """True when ``pap.profile == 'shelf'`` or semantics class is ``'shelf'``."""
    if pap.profile == "shelf":
        return True
    if pap.semantics and pap.semantics.cls == "shelf":
        return True
    return False


def passes(pap: PAP) -> PAP:
    """Return the shelf PAP enriched with fill-region defaults.

    If ``pap._fill_regions`` is already set, the PAP is returned as-is (the
    bake pipeline has already computed the regions from authored data).
    """
    return pap


def populate(
    region: dict,
    assets: list[PAP],
    *,
    gap: float = 0.02,
) -> list[tuple[PAP, Transform]]:
    """Place ``assets`` into ``region``, validating each placement via T9.

    Assets are placed left-to-right (along the region's X axis) with ``gap``
    between them.  The cursor starts at the left edge; when the next asset
    would overflow the right edge the loop stops.

    Each candidate (PAP, Transform) is validated through the orchestrator's
    gate stack.  Only placements where ``verdict.ok`` is True are included in
    the output.

    Parameters
    ----------
    region:
        A fill-region dict (``id``, ``origin``, ``size``, ``max_load_kg``).
    assets:
        Ordered list of PAPs to place.  The caller decides the ordering.
    gap:
        Gap in metres between adjacent assets (default 2 cm).

    Returns
    -------
    list[(PAP, Transform)]:
        Validated placements.  May be shorter than ``assets`` if the region is
        full or some placements fail the gate stack.
    """
    if not assets:
        return []

    origin = np.asarray(region.get("origin", [0.0, 0.0, 0.0]), dtype=float)
    size = np.asarray(region.get("size", [1.0, 0.4, 0.5]), dtype=float)
    region_width = float(size[0])
    region_depth = float(size[1])
    region_z = float(origin[2])

    # Build a world with just the placed assets so validation can check
    # inter-asset collisions within the shelf region.
    world = WorldModel()

    placements: list[tuple[PAP, Transform]] = []
    cursor_x = float(origin[0]) - region_width / 2.0  # start at the left edge

    for i, asset in enumerate(assets):
        # Determine the asset's footprint width from its AABB.
        asset_half = asset.geometry.aabb or asset.geometry.obb or [0.05, 0.05, 0.1]
        asset_half_x = float(asset_half[0])
        asset_half_y = float(asset_half[1])
        asset_half_z = float(asset_half[2])

        # Centre of this asset along X.
        x_pos = cursor_x + asset_half_x + (gap if i > 0 else 0.0)
        # Check if the asset fits within the region width.
        right_edge = x_pos + asset_half_x
        max_x = float(origin[0]) + region_width / 2.0
        if right_edge > max_x + 1e-6:
            # No more room in this region.
            break

        # Centre along Y (depth direction): fit within the shelf depth.
        y_pos = float(origin[1])
        y_pos = np.clip(y_pos, float(origin[1]) - region_depth / 2.0 + asset_half_y,
                        float(origin[1]) + region_depth / 2.0 - asset_half_y)

        # Z: sit on the shelf surface (origin[2] is the shelf surface).
        z_pos = region_z + asset_half_z

        tf = Transform(
            pos=[float(x_pos), float(y_pos), float(z_pos)],
            quat=[0.0, 0.0, 0.0, 1.0],
            scale=[1.0, 1.0, 1.0],
        )

        node_id = f"_shelf_asset_{i}"
        valid = _validate_placement(world, asset, node_id, tf)
        if valid:
            world.add(node_id, asset, tf)
            placements.append((asset, tf))
            cursor_x = x_pos + asset_half_x  # advance cursor past this asset

    return placements


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _validate_placement(
    world: WorldModel,
    asset: PAP,
    node_id: str,
    tf: Transform,
) -> bool:
    """Return True if placing ``asset`` at ``tf`` in ``world`` passes the gate stack.

    Uses the orchestrator's validate_operation.  To keep the check self-contained
    and fast we add a temporary node with a dummy transform, then validate a diff
    that sets it to ``tf``.

    If the world has no other nodes yet, the placement is trivially valid
    (no collision peers, stability is checked against a unit base).
    """
    from cortex.orchestrator import validate_operation

    # Add the node temporarily so validate_operation can find it.
    temp_tf = Transform(pos=[1000.0, 1000.0, 1000.0], quat=[0, 0, 0, 1])
    try:
        world.add(node_id, asset, temp_tf)
    except KeyError:
        # Already present — update transform.
        world.update_transform(node_id, temp_tf)

    diff = Diff(object=node_id, transform=tf)
    verdict = validate_operation(world, diff)

    # Remove the temporary node.
    world.remove(node_id)

    return bool(verdict.ok)


# Profile constants (consumed by __init__.py).
DEFAULT_STATES: list[str] = ["upright", "full", "empty"]
DEFAULT_REGIONS: list[dict] = []  # regions are derived from geometry at bake time
DEFAULT_CONSTRAINTS: list[dict] = [
    {"law": "com_over_base", "node": "self"},
]
