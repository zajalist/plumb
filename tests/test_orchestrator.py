"""
Tests for cortex/orchestrator.py (Task 9) — validate_operation.

validate_operation(world, diff, laws=None) -> Verdict

Applies diff to a copy of the world, runs gates left→right:
  collision → stability → constraints → reach
Halts at the first hard failure (later gates skipped=True).

Tests:
1. Topple diff → stopped_at=stability, collision ok, stability fail, constraints+reach skipped.
2. After repair diff → ok True, nothing skipped.
3. Collision hard-fail halts before stability (stability + later gates skipped).
4. All gates pass → ok True, stopped_at=None, no gates skipped.
5. Verdict is a valid contracts.Verdict with schema_version.
6. soft_cost populated from constraints gate soft violations.
"""

from __future__ import annotations

import math

import numpy as np

from contracts import (
    Diff,
    GateName,
    Geometry,
    PAP,
    Physical,
    Semantics,
    Structural,
    Transform,
    Verdict,
)
from cortex.bake.physical import bake_physical
from cortex.gates.stability import stability, STABILITY_MARGIN_M
from cortex.orchestrator import validate_operation
from cortex.repair import suggest_transform
from cortex.world import WorldModel
from tests.helpers import make_box, two_part_topheavy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _square_footprint(half: float, center=(0.0, 0.0)) -> list[list[float]]:
    cx, cy = center
    return [
        [cx - half, cy - half],
        [cx + half, cy - half],
        [cx + half, cy + half],
        [cx - half, cy + half],
    ]


def _identity() -> Transform:
    return Transform(pos=[0.0, 0.0, 0.0])


def _make_topple_pap() -> PAP:
    """Top-heavy bronze figure PAP placed at pedestal edge — CoM ~7cm outside footprint."""
    parts, materials = two_part_topheavy()
    phys = bake_physical(parts, {0: materials["base"], 1: materials["body"]})
    # Footprint centred at x = −0.27 → right edge at −0.07; CoM at x=0 → 7cm outside.
    footprint = _square_footprint(0.2, center=(-0.27, 0.0))
    return PAP(
        asset_id="bronze_figure",
        geometry=Geometry(
            aabb=[0.2, 0.2, 0.65],
            obb=[0.2, 0.2, 0.65],
            volume_m3=0.01,
            convex_parts=2,
        ),
        physical=Physical(mass_kg=float(phys.mass_kg), com=list(phys.com)),
        structural=Structural(support_footprint=footprint),
        semantics=Semantics(front=[0.0, 1.0, 0.0]),
    )


def _make_stable_pap() -> PAP:
    """A simple box PAP with CoM centred over its footprint — always stable."""
    return PAP(
        asset_id="stable_box",
        geometry=Geometry(
            aabb=[0.3, 0.3, 0.5],
            obb=[0.3, 0.3, 0.5],
            volume_m3=0.09,
            convex_parts=1,
        ),
        physical=Physical(mass_kg=10.0, com=[0.0, 0.0, 0.3]),
        structural=Structural(support_footprint=_square_footprint(0.3)),
        semantics=Semantics(front=[0.0, 1.0, 0.0]),
    )


def _topple_world() -> tuple[WorldModel, str]:
    """A world with the topple fixture at identity transform; no other nodes."""
    pap = _make_topple_pap()
    world = WorldModel()
    world.add("figure", pap, _identity())
    return world, "figure"


def _stable_world() -> tuple[WorldModel, str]:
    """A world with a stable box at identity transform; no other nodes."""
    pap = _make_stable_pap()
    world = WorldModel()
    world.add("box", pap, _identity())
    return world, "box"


def _overlapping_world() -> tuple[WorldModel, str, str]:
    """A world with two overlapping boxes — collision gate must fail."""
    box_pap = _make_stable_pap()
    box2_pap = PAP(
        asset_id="blocker",
        geometry=Geometry(aabb=[0.3, 0.3, 0.5], obb=[0.3, 0.3, 0.5], volume_m3=0.09, convex_parts=1),
        physical=Physical(mass_kg=10.0, com=[0.0, 0.0, 0.3]),
        structural=Structural(support_footprint=_square_footprint(0.3)),
        semantics=Semantics(front=[0.0, 1.0, 0.0]),
    )
    world = WorldModel()
    # box at origin, blocker at same position → deep overlap
    world.add("box", box_pap, _identity())
    world.add("blocker", box2_pap, _identity())
    return world, "box", "blocker"


# ---------------------------------------------------------------------------
# Test 1: topple diff → stopped_at=stability, collision ok, stability fail,
#         constraints+reach skipped
# ---------------------------------------------------------------------------
def test_topple_verdict_shape():
    """The headline bet: topple diff reproduces VERDICT_TOPPLE shape."""
    world, obj_id = _topple_world()
    diff = Diff(object=obj_id, transform=_identity())

    verdict = validate_operation(world, diff)

    assert isinstance(verdict, Verdict)
    assert verdict.ok is False
    assert verdict.stopped_at == GateName.stability

    # Exactly 4 gates.
    assert len(verdict.gates) == 4
    gate_names = [g.gate for g in verdict.gates]
    assert gate_names == [
        GateName.collision,
        GateName.stability,
        GateName.constraints,
        GateName.reach,
    ]

    # Collision ok (no other nodes → infinite clearance or positive clearance).
    col = verdict.gates[0]
    assert col.gate == GateName.collision
    assert col.ok is True
    assert col.skipped is False

    # Stability fail.
    stab = verdict.gates[1]
    assert stab.gate == GateName.stability
    assert stab.ok is False
    assert stab.skipped is False
    # margin should be around -0.07 (pedestal-edge fixture).
    assert stab.value_m is not None and stab.value_m < 0

    # Constraints + reach skipped.
    con = verdict.gates[2]
    assert con.gate == GateName.constraints
    assert con.skipped is True
    assert con.ok is None

    rch = verdict.gates[3]
    assert rch.gate == GateName.reach
    assert rch.skipped is True
    assert rch.ok is None


# ---------------------------------------------------------------------------
# Test 2: after repair diff → ok True, nothing skipped
# ---------------------------------------------------------------------------
def test_repaired_verdict_all_pass():
    """After suggest_transform the diff should produce ok=True with nothing skipped."""
    world, obj_id = _topple_world()

    # Compute the repaired transform.
    repaired_tf = suggest_transform(world, obj_id, {})

    diff = Diff(object=obj_id, transform=repaired_tf)
    verdict = validate_operation(world, diff)

    assert isinstance(verdict, Verdict)
    assert verdict.ok is True
    assert verdict.stopped_at is None

    # All gates ran (none skipped).
    for g in verdict.gates:
        assert g.skipped is False, f"gate {g.gate} should not be skipped after repair"
        assert g.ok is True, f"gate {g.gate} should be ok after repair"


# ---------------------------------------------------------------------------
# Test 3: collision hard-fail halts before stability
# ---------------------------------------------------------------------------
def test_collision_hard_fail_stops_before_stability():
    """When collision gate fails, stability and later gates are skipped."""
    world, box_id, _ = _overlapping_world()
    # Move box to same position as blocker (both at origin → overlap).
    diff = Diff(object=box_id, transform=_identity())

    verdict = validate_operation(world, diff)

    assert verdict.ok is False
    assert verdict.stopped_at == GateName.collision

    gate_names = [g.gate for g in verdict.gates]
    assert gate_names == [
        GateName.collision,
        GateName.stability,
        GateName.constraints,
        GateName.reach,
    ]

    # Collision fails.
    col = verdict.gates[0]
    assert col.ok is False
    assert col.skipped is False

    # Everything after is skipped.
    for g in verdict.gates[1:]:
        assert g.skipped is True, f"gate {g.gate} should be skipped after collision fail"
        assert g.ok is None


# ---------------------------------------------------------------------------
# Test 4: all gates pass → ok True, stopped_at=None, nothing skipped
# ---------------------------------------------------------------------------
def test_all_gates_pass_stable_world():
    """A stable world with no collisions, no laws → all gates pass."""
    world, obj_id = _stable_world()
    diff = Diff(object=obj_id, transform=_identity())

    verdict = validate_operation(world, diff, laws=None)

    assert isinstance(verdict, Verdict)
    assert verdict.ok is True
    assert verdict.stopped_at is None
    for g in verdict.gates:
        assert g.skipped is False
        assert g.ok is True


# ---------------------------------------------------------------------------
# Test 5: Verdict is a valid contracts.Verdict with schema_version
# ---------------------------------------------------------------------------
def test_verdict_has_schema_version():
    """validate_operation must return a Verdict with a schema_version field."""
    from contracts import SCHEMA_VERSION
    world, obj_id = _stable_world()
    diff = Diff(object=obj_id, transform=_identity())

    verdict = validate_operation(world, diff)

    assert isinstance(verdict, Verdict)
    assert verdict.schema_version == SCHEMA_VERSION
    assert len(verdict.gates) == 4
    assert isinstance(verdict.soft_cost, float)


# ---------------------------------------------------------------------------
# Test 6: soft_cost propagated from constraints gate (when laws are provided)
# ---------------------------------------------------------------------------
def test_soft_cost_from_constraints_laws():
    """When facing laws are provided and violated, soft_cost > 0 in the Verdict."""
    world, obj_id = _stable_world()

    # Add a facing law: the box's front [0,1,0] needs to face [10, 0, 0].
    # That's 90° off, which violates any reasonable tolerance.
    laws = [
        {
            "law": "facing",
            "node": obj_id,
            "target": [10.0, 0.0, 0.0],
            "tol_deg": 5.0,
        }
    ]

    diff = Diff(object=obj_id, transform=_identity())
    verdict = validate_operation(world, diff, laws=laws)

    # Facing is soft, so the gate should still be ok (soft never gates).
    assert verdict.ok is True
    # soft_cost should reflect the violation magnitude (85° over 5°).
    assert verdict.soft_cost > 0.0


# ---------------------------------------------------------------------------
# Test 7: diff does NOT mutate the original world
# ---------------------------------------------------------------------------
def test_diff_does_not_mutate_world():
    """validate_operation must apply the diff to a COPY — the original world is unchanged."""
    world, obj_id = _topple_world()
    original_tf = world.get(obj_id).transform
    original_pos = list(original_tf.pos)

    # Apply a diff with a different transform.
    new_tf = Transform(pos=[5.0, 5.0, 0.0])
    diff = Diff(object=obj_id, transform=new_tf)
    validate_operation(world, diff)

    # Original world must be unchanged.
    after_tf = world.get(obj_id).transform
    assert list(after_tf.pos) == original_pos, (
        "validate_operation must not mutate the original world"
    )
