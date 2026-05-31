"""
Tests for cortex/gates/collision.py (Task 5) — the Collision gate.

The gate computes the signed clearance between the convex parts of node ``a``
and the convex parts of node ``b`` (or all other nodes when ``b`` is None).

  * ``value_m >= 0``  → clearance (no penetration), ``ok = True``
  * ``value_m < 0``   → penetration depth (negative), ``ok = False``
  * On penetration, ``fix.translate`` separates along the contact normal.

Deterministic trimesh primitives only (tests/helpers.py). No external downloads.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from contracts import (
    GateName,
    GateResult,
    Geometry,
    PAP,
    Physical,
    Transform,
)
from cortex.gates.collision import collision
from cortex.world import WorldModel
from tests.helpers import make_box


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _make_world_with_boxes(
    a_extents=(1.0, 1.0, 1.0),
    a_pos=(0.0, 0.0, 0.0),
    b_extents=(1.0, 1.0, 1.0),
    b_pos=(2.0, 0.0, 0.0),
) -> WorldModel:
    """Two named box nodes in a fresh WorldModel."""
    world = WorldModel()
    pap_a = _box_pap("box_a", a_extents)
    pap_b = _box_pap("box_b", b_extents)
    world.add("box_a", pap_a, Transform(pos=list(a_pos)))
    world.add("box_b", pap_b, Transform(pos=list(b_pos)))
    return world


def _box_pap(asset_id: str, extents=(1.0, 1.0, 1.0)) -> PAP:
    """Minimal PAP for an axis-aligned box, with geometry baked from a trimesh box."""
    from cortex.bake.geometry import bake_geometry_parts
    from tests.helpers import save_mesh_tmp

    mesh = make_box(extents=extents)
    path = save_mesh_tmp(mesh)
    geometry, _parts, _flag = bake_geometry_parts(path)
    # Attach the convex parts to the PAP so the collision gate can consume them.
    pap = PAP(
        asset_id=asset_id,
        geometry=geometry,
        physical=Physical(mass_kg=1.0, com=[0.0, 0.0, 0.0]),
    )
    # Store parts on the pap for the gate (the gate reads pap._convex_parts if present).
    pap._convex_parts = _parts  # type: ignore[attr-defined]
    return pap


# --------------------------------------------------------------------------- #
# Test 1 — Two boxes clearly apart → positive clearance, ok True
# --------------------------------------------------------------------------- #
def test_boxes_apart_positive_clearance():
    """Two unit boxes 2 m apart (surface-to-surface gap = 1 m) → clearance ≥ 0, ok."""
    world = _make_world_with_boxes(
        a_pos=(0.0, 0.0, 0.0),
        b_pos=(2.0, 0.0, 0.0),
    )
    result = collision(world, "box_a", "box_b")
    assert isinstance(result, GateResult)
    assert result.gate == GateName.collision
    assert result.ok is True
    assert result.value_m is not None
    assert result.value_m > 0
    assert result.skipped is False


# --------------------------------------------------------------------------- #
# Test 2 — Overlapping boxes → negative clearance (penetration), ok False
# --------------------------------------------------------------------------- #
def test_boxes_overlapping_negative_clearance():
    """Two unit boxes sharing the same centre → penetration, ok False, fix separates."""
    world = _make_world_with_boxes(
        a_pos=(0.0, 0.0, 0.0),
        b_pos=(0.0, 0.0, 0.0),
    )
    result = collision(world, "box_a", "box_b")
    assert result.ok is False
    assert result.value_m is not None
    assert result.value_m < 0
    assert result.fix is not None
    # The fix translate must be non-zero.
    fix = np.asarray(result.fix.translate)
    assert np.linalg.norm(fix) > 0


# --------------------------------------------------------------------------- #
# Test 3 — Applying the fix separates the boxes
# --------------------------------------------------------------------------- #
def test_fix_separates_overlapping_boxes():
    """Applying fix.translate to node b's position resolves the penetration."""
    world = _make_world_with_boxes(
        a_pos=(0.0, 0.0, 0.0),
        b_pos=(0.0, 0.0, 0.0),
    )
    result = collision(world, "box_a", "box_b")
    assert result.ok is False
    fix = result.fix.translate

    # Move box_b by the fix vector.
    old_pos = world.get("box_b").transform.pos
    new_pos = [old_pos[i] + fix[i] for i in range(3)]
    world.update_transform("box_b", Transform(pos=new_pos))

    result2 = collision(world, "box_a", "box_b")
    assert result2.ok is True
    assert result2.value_m is not None
    assert result2.value_m >= 0


# --------------------------------------------------------------------------- #
# Test 4 — Touching boxes → value_m ≈ 0
# --------------------------------------------------------------------------- #
def test_boxes_touching_approx_zero():
    """Two unit boxes touching face-to-face (gap = 0) → value_m ≈ 0."""
    # Unit box spans [-0.5, 0.5] in each axis; touching when centres are 1.0 apart.
    world = _make_world_with_boxes(
        a_extents=(1.0, 1.0, 1.0),
        a_pos=(0.0, 0.0, 0.0),
        b_extents=(1.0, 1.0, 1.0),
        b_pos=(1.0, 0.0, 0.0),
    )
    result = collision(world, "box_a", "box_b")
    assert result.value_m is not None
    # The gap is ≈ 0; allow for small numerical error from convex hull.
    assert abs(result.value_m) < 0.05


# --------------------------------------------------------------------------- #
# Test 5 — b=None checks against ALL other nodes
# --------------------------------------------------------------------------- #
def test_b_none_checks_all_other_nodes():
    """collision(world, 'box_a', b=None) finds the min clearance over all other nodes."""
    world = WorldModel()
    pap_a = _box_pap("box_a")
    pap_b = _box_pap("box_b")
    pap_c = _box_pap("box_c")
    world.add("box_a", pap_a, Transform(pos=[0.0, 0.0, 0.0]))
    # box_b is far away (clear)
    world.add("box_b", pap_b, Transform(pos=[10.0, 0.0, 0.0]))
    # box_c overlaps with box_a
    world.add("box_c", pap_c, Transform(pos=[0.0, 0.0, 0.0]))

    result = collision(world, "box_a", None)
    # Even though box_b is clear, box_c overlaps → overall not ok.
    assert result.ok is False
    assert result.value_m is not None
    assert result.value_m < 0


# --------------------------------------------------------------------------- #
# Test 6 — Single node world: b=None with no other nodes → ok, clearance infinite
# --------------------------------------------------------------------------- #
def test_b_none_single_node_ok():
    """A world with only one node: no possible collision → ok True."""
    world = WorldModel()
    pap_a = _box_pap("box_a")
    world.add("box_a", pap_a, Transform(pos=[0.0, 0.0, 0.0]))

    result = collision(world, "box_a", None)
    assert result.ok is True
    assert result.skipped is False


# --------------------------------------------------------------------------- #
# Test 7 — Gate name is correct
# --------------------------------------------------------------------------- #
def test_gate_name_is_collision():
    """GateResult.gate must be GateName.collision."""
    world = _make_world_with_boxes()
    result = collision(world, "box_a", "box_b")
    assert result.gate == GateName.collision
