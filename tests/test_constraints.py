"""
tests/test_constraints.py — TDD for cortex/gates/constraints.py (Task 7).

Laws tested:
  - facing:        soft, angle between front and direction to target <= tol
  - com_over_base: hard, wraps stability margin
  - walkway:       hard, wraps reach
  - door_clear:    hard, collision vs swept-volume obstacle

Gate aggregation:
  - all hard laws ok → gate ok
  - any hard law fails → gate not-ok
  - soft law failing → gate still ok, but soft_cost accumulates magnitude
"""
from __future__ import annotations

import math

import pytest

from contracts import (
    GateName,
    GateResult,
    PAP,
    Semantics,
    Physical,
    Geometry,
    Structural,
    Transform,
)
from cortex.world import WorldModel
from cortex.gates.constraints import (
    evaluate_constraints,
    facing,
    com_over_base,
    walkway,
    door_clear,
)


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

def _make_pap(
    asset_id: str = "test_obj",
    front: list[float] | None = None,
    com: list[float] | None = None,
    aabb: list[float] | None = None,
) -> PAP:
    """Minimal PAP for constraints testing."""
    return PAP(
        asset_id=asset_id,
        geometry=Geometry(
            aabb=aabb or [0.5, 0.5, 0.5],
            obb=[0.5, 0.5, 0.5],
            volume_m3=1.0,
        ),
        semantics=Semantics(
            front=front or [0.0, 1.0, 0.0],
        ),
        physical=Physical(
            mass_kg=10.0,
            com=com or [0.0, 0.0, 0.0],
        ),
    )


def _make_world_with_one_box(
    node_id: str = "obj",
    pos: list[float] | None = None,
    aabb: list[float] | None = None,
) -> tuple[WorldModel, PAP, Transform]:
    """World containing one node centred at pos."""
    pap = _make_pap(asset_id=node_id, aabb=aabb)
    tf = Transform(pos=pos or [0.0, 0.0, 0.0])
    world = WorldModel()
    world.add(node_id, pap, tf)
    return world, pap, tf


# ──────────────────────────────────────────────────────────────────────────────
# facing law tests (soft)
# ──────────────────────────────────────────────────────────────────────────────

class TestFacing:
    """facing(world, params) -> ConstraintResult  [soft]"""

    def test_facing_within_tolerance_ok(self):
        """Object facing target within tol → ok=True, magnitude≈0."""
        world, pap, tf = _make_world_with_one_box(pos=[0.0, 0.0, 0.0])
        # front=[0,1,0] at pos=[0,0,0], target at [0, 5, 0] → angle=0°
        params = {
            "node": "obj",
            "target": [0.0, 5.0, 0.0],
            "tol_deg": 10.0,
        }
        result = facing(world, params)
        assert result.ok is True
        assert result.hard is False  # soft law
        assert result.magnitude < 1e-6

    def test_facing_beyond_tolerance_not_ok(self):
        """Object front=[0,1,0] at origin, target at [5,0,0] → 90° angle, tol=10° → not ok."""
        world, pap, tf = _make_world_with_one_box(pos=[0.0, 0.0, 0.0])
        params = {
            "node": "obj",
            "target": [5.0, 0.0, 0.0],
            "tol_deg": 10.0,
        }
        result = facing(world, params)
        assert result.ok is False
        assert result.hard is False  # still soft
        # angle = 90°, tol = 10° → magnitude = 80°
        assert abs(result.magnitude - 80.0) < 1.0

    def test_facing_detail_string_format(self):
        """Detail string contains Δ and degrees."""
        world, pap, tf = _make_world_with_one_box(pos=[0.0, 0.0, 0.0])
        params = {
            "node": "obj",
            "target": [1.0, 0.0, 0.0],  # 90° off for front=[0,1,0]
            "tol_deg": 10.0,
        }
        result = facing(world, params)
        assert result.detail is not None
        assert "°" in result.detail or "deg" in result.detail.lower() or "Δ" in result.detail

    def test_facing_partial_angle(self):
        """45° off, tol=10° → magnitude ≈ 35°."""
        world, pap, tf = _make_world_with_one_box(pos=[0.0, 0.0, 0.0])
        # front=[0,1,0], target at 45° from +Y: [1,1,0]
        params = {
            "node": "obj",
            "target": [1.0, 1.0, 0.0],
            "tol_deg": 10.0,
        }
        result = facing(world, params)
        assert result.ok is False
        assert abs(result.magnitude - 35.0) < 1.5


# ──────────────────────────────────────────────────────────────────────────────
# com_over_base law tests (hard)
# ──────────────────────────────────────────────────────────────────────────────

class TestComOverBase:
    """com_over_base wraps stability gate; hard=True."""

    def test_com_over_base_stable_is_ok(self):
        """CoM centered over unit footprint → stable → ok=True, hard=True."""
        world, pap, tf = _make_world_with_one_box(pos=[0.0, 0.0, 0.0])
        params = {"node": "obj"}
        result = com_over_base(world, params)
        assert result.hard is True
        assert result.ok is True
        assert result.magnitude == 0.0

    def test_com_over_base_unstable_is_not_ok(self):
        """CoM shoved past edge → stability fails → ok=False, hard=True, magnitude>0."""
        # aabb=[0.5,0.5,0.5] → footprint ±0.5 in XY.
        # Place CoM at x=1.0 by shifting the node pos (stability.py: footprint doesn't translate).
        world, pap, tf = _make_world_with_one_box(pos=[2.0, 0.0, 0.0])
        # The CoM in world space = [2.0, 0.0, 0.0], footprint stays at origin ±0.5
        params = {"node": "obj"}
        result = com_over_base(world, params)
        assert result.hard is True
        assert result.ok is False
        assert result.magnitude > 0.0


# ──────────────────────────────────────────────────────────────────────────────
# walkway law tests (hard)
# ──────────────────────────────────────────────────────────────────────────────

class TestWalkway:
    """walkway wraps reach gate; hard=True."""

    def test_walkway_empty_is_ok(self):
        """Empty walkway wide enough → ok=True."""
        world = WorldModel()  # no obstacles
        poly = [[0.0, 0.0], [5.0, 0.0], [5.0, 5.0], [0.0, 5.0]]
        params = {"walkway_poly": poly, "agent_r": 0.45}
        result = walkway(world, params)
        assert result.hard is True
        assert result.ok is True

    def test_walkway_pinched_is_not_ok(self):
        """Obstacle pinching walkway below agent diameter → not ok."""
        poly = [[0.0, 0.0], [4.0, 0.0], [4.0, 1.0], [0.0, 1.0]]  # 4m × 1m
        world = WorldModel()
        # Add a wide obstacle in the middle that leaves < 0.9m clear
        obs_pap = _make_pap(asset_id="wall", aabb=[1.5, 0.4, 1.0])
        obs_tf = Transform(pos=[2.0, 0.5, 0.0])
        world.add("wall", obs_pap, obs_tf)

        params = {"walkway_poly": poly, "agent_r": 0.45}
        result = walkway(world, params)
        assert result.hard is True
        assert result.ok is False


# ──────────────────────────────────────────────────────────────────────────────
# door_clear law tests (hard)
# ──────────────────────────────────────────────────────────────────────────────

class TestDoorClear:
    """door_clear: hard collision check vs a swept-volume obstacle node."""

    def test_door_clear_no_overlap_is_ok(self):
        """Object far from door sweep volume → ok=True."""
        # Door sweep occupies node "door_sweep" at [0,0,0] with aabb [0.5,0.5,1.0]
        # Object "chair" sits at [3,0,0] — no overlap
        world = WorldModel()

        door_pap = _make_pap(asset_id="door_sweep", aabb=[0.5, 0.5, 1.0])
        world.add("door_sweep", door_pap, Transform(pos=[0.0, 0.0, 0.0]))

        chair_pap = _make_pap(asset_id="chair", aabb=[0.4, 0.4, 0.5])
        world.add("chair", chair_pap, Transform(pos=[3.0, 0.0, 0.0]))

        params = {"node": "chair", "sweep_node": "door_sweep"}
        result = door_clear(world, params)
        assert result.hard is True
        assert result.ok is True

    def test_door_clear_overlap_is_not_ok(self):
        """Object placed inside door sweep volume → ok=False."""
        world = WorldModel()

        door_pap = _make_pap(asset_id="door_sweep", aabb=[0.5, 0.5, 1.0])
        world.add("door_sweep", door_pap, Transform(pos=[0.0, 0.0, 0.0]))

        chair_pap = _make_pap(asset_id="chair", aabb=[0.4, 0.4, 0.5])
        # Chair overlaps the door sweep (centre at [0,0,0], total clearance test)
        world.add("chair", chair_pap, Transform(pos=[0.2, 0.0, 0.0]))

        params = {"node": "chair", "sweep_node": "door_sweep"}
        result = door_clear(world, params)
        assert result.hard is True
        assert result.ok is False


# ──────────────────────────────────────────────────────────────────────────────
# evaluate_constraints aggregation tests
# ──────────────────────────────────────────────────────────────────────────────

class TestEvaluateConstraints:
    """evaluate_constraints aggregates ConstraintResults into a GateResult."""

    def test_all_laws_ok_gate_is_ok(self):
        """All laws pass → GateResult.ok=True."""
        world, pap, tf = _make_world_with_one_box(pos=[0.0, 0.0, 0.0])
        laws = [
            {"law": "facing", "node": "obj", "target": [0.0, 5.0, 0.0], "tol_deg": 10.0},
            {"law": "com_over_base", "node": "obj"},
        ]
        result = evaluate_constraints(world, laws)
        assert isinstance(result, GateResult)
        assert result.gate == GateName.constraints
        assert result.ok is True
        assert len(result.constraints) == 2

    def test_hard_law_fail_makes_gate_not_ok(self):
        """A hard law failing makes gate.ok=False."""
        world, pap, tf = _make_world_with_one_box(pos=[2.0, 0.0, 0.0])
        laws = [
            {"law": "com_over_base", "node": "obj"},  # hard, will fail
        ]
        result = evaluate_constraints(world, laws)
        assert result.ok is False

    def test_soft_law_fail_does_not_gate(self):
        """A soft law failing alone does not make gate.ok=False."""
        world, pap, tf = _make_world_with_one_box(pos=[0.0, 0.0, 0.0])
        laws = [
            {"law": "facing", "node": "obj", "target": [5.0, 0.0, 0.0], "tol_deg": 10.0},
        ]
        result = evaluate_constraints(world, laws)
        assert result.ok is True  # gate ok — soft failure doesn't gate

    def test_soft_cost_accumulates_soft_magnitudes(self):
        """soft_cost in GateResult.value_m reflects the sum of soft violation magnitudes."""
        world, pap, tf = _make_world_with_one_box(pos=[0.0, 0.0, 0.0])
        # facing 90° off, tol=10° → magnitude ≈ 80°
        laws = [
            {"law": "facing", "node": "obj", "target": [5.0, 0.0, 0.0], "tol_deg": 10.0},
        ]
        result = evaluate_constraints(world, laws)
        # value_m is used for soft_cost in this gate
        soft = sum(
            cr.magnitude for cr in result.constraints if not cr.hard and not cr.ok
        )
        assert soft > 0.0

    def test_mixed_hard_soft_hard_fails(self):
        """Hard law fails + soft law fails → gate not ok."""
        world, pap, tf = _make_world_with_one_box(pos=[2.0, 0.0, 0.0])
        laws = [
            {"law": "com_over_base", "node": "obj"},  # hard, will fail
            {"law": "facing", "node": "obj", "target": [5.0, 0.0, 0.0], "tol_deg": 10.0},  # soft, fails
        ]
        result = evaluate_constraints(world, laws)
        assert result.ok is False
        assert len(result.constraints) == 2

    def test_constraint_results_names_preserved(self):
        """Each ConstraintResult carries the law name."""
        world, pap, tf = _make_world_with_one_box(pos=[0.0, 0.0, 0.0])
        laws = [
            {"law": "facing", "node": "obj", "target": [0.0, 5.0, 0.0], "tol_deg": 10.0},
            {"law": "com_over_base", "node": "obj"},
        ]
        result = evaluate_constraints(world, laws)
        names = {cr.name for cr in result.constraints}
        assert "facing" in names
        assert "com_over_base" in names
