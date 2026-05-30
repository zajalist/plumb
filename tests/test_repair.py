"""
Tests for cortex/repair.py (Task 8) — suggest_transform (the "repair").

suggest_transform(world, obj, intent) -> Transform

Builds an objective over [dx, dy, dyaw] decision vars:
  - Hard constraints: stability margin >= STABILITY_MARGIN_M, collision clearance >= 0
  - Soft objective: facing magnitude + small movement penalty
  - Solver: scipy.optimize.minimize(method="SLSQP")
  - Fallback: if SLSQP fails, applies stability gate's fix.translate directly

Tests:
1. Topple fixture → returned transform makes stability().ok True
2. Returned transform is a valid Transform
3. Starting from a stable position → returns a transform still stable
4. Collision-aware repair: when sliding would collide, solver still returns
   a stability-valid transform (greedy fallback also qualifies)
5. Yaw-only intent is reflected in the returned transform (quat changes)
6. Movement penalty keeps the repair small when already near-stable
"""

from __future__ import annotations

import math

import numpy as np

from contracts import (
    PAP,
    Geometry,
    GateName,
    Physical,
    Semantics,
    Structural,
    Transform,
)
from cortex.bake.physical import bake_physical
from cortex.gates.stability import stability, STABILITY_MARGIN_M
from cortex.repair import suggest_transform
from cortex.world import WorldModel
from tests.helpers import make_box, two_part_topheavy


# ---------------------------------------------------------------------------
# Fixtures / helpers
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
    """Top-heavy bronze figure PAP with the pedestal-edge footprint from T4 demo."""
    parts, materials = two_part_topheavy()
    phys = bake_physical(parts, {0: materials["base"], 1: materials["body"]})
    # Footprint: pedestal-edge so CoM lands ~7cm outside the near edge.
    footprint = _square_footprint(0.2, center=(-0.27, 0.0))
    return PAP(
        asset_id="bronze_figure",
        geometry=Geometry(aabb=[0.2, 0.2, 0.65], obb=[0.2, 0.2, 0.65], volume_m3=0.01, convex_parts=2),
        physical=Physical(mass_kg=float(phys.mass_kg), com=list(phys.com)),
        structural=Structural(support_footprint=footprint),
        semantics=Semantics(front=[0.0, 1.0, 0.0]),
    )


def _make_stable_pap() -> PAP:
    """A simple stable PAP with CoM centred over its footprint."""
    return PAP(
        asset_id="stable_box",
        geometry=Geometry(aabb=[0.3, 0.3, 0.5], obb=[0.3, 0.3, 0.5], volume_m3=0.09, convex_parts=1),
        physical=Physical(mass_kg=10.0, com=[0.0, 0.0, 0.3]),
        structural=Structural(support_footprint=_square_footprint(0.3)),
        semantics=Semantics(front=[0.0, 1.0, 0.0]),
    )


def _world_with_one(pap: PAP, node_id: str = "obj", transform: Transform | None = None) -> WorldModel:
    world = WorldModel()
    tf = transform or _identity()
    world.add(node_id, pap, tf)
    return world


def _world_with_obstacle() -> tuple[WorldModel, str]:
    """World with a topple fixture and a blocker that would be collided if we slide right."""
    # Topple figure at origin.
    figure_pap = _make_topple_pap()

    # A big wall at x = +0.5 (so sliding right to fix the CoM would hit it).
    wall_box = make_box(extents=(0.1, 2.0, 2.0), center=(0.5, 0.0, 1.0))
    wall_pap = PAP(
        asset_id="wall",
        geometry=Geometry(aabb=[0.05, 1.0, 1.0], obb=[0.05, 1.0, 1.0], volume_m3=0.2, convex_parts=1),
        physical=Physical(mass_kg=100.0, com=[0.5, 0.0, 1.0]),
        structural=Structural(),
        semantics=Semantics(),
    )
    wall_pap._convex_parts = [wall_box]  # type: ignore[attr-defined]

    world = WorldModel()
    world.add("figure", figure_pap, _identity())
    world.add("wall", wall_pap, _identity())
    return world, "figure"


# ---------------------------------------------------------------------------
# Test 1: topple fixture → repair produces a stability-valid transform
# ---------------------------------------------------------------------------
def test_repair_topple_fixture_stability_ok():
    """The primary bet: suggest_transform on the topple fixture returns a Transform
    for which stability().ok is True."""
    pap = _make_topple_pap()
    world = _world_with_one(pap)

    # Confirm it is currently unstable.
    initial_tf = world.get("obj").transform
    assert not stability(pap, initial_tf).ok, "fixture must start unstable"

    intent = {}
    result_tf = suggest_transform(world, "obj", intent)

    res = stability(pap, result_tf)
    assert res.ok, (
        f"suggest_transform must return a stable transform; "
        f"got margin={res.value_m:.4f}"
    )


# ---------------------------------------------------------------------------
# Test 2: returned value is a valid Transform
# ---------------------------------------------------------------------------
def test_repair_returns_valid_transform():
    """Return type must be a contracts.Transform with pos/quat/scale of correct lengths."""
    pap = _make_topple_pap()
    world = _world_with_one(pap)
    result_tf = suggest_transform(world, "obj", {})

    assert isinstance(result_tf, Transform)
    assert len(result_tf.pos) == 3
    assert len(result_tf.quat) == 4
    assert len(result_tf.scale) == 3

    # Quaternion should be normalised (unit quaternion).
    q = np.asarray(result_tf.quat, dtype=float)
    assert math.isclose(float(np.linalg.norm(q)), 1.0, abs_tol=1e-6)


# ---------------------------------------------------------------------------
# Test 3: starting from a stable position stays stable
# ---------------------------------------------------------------------------
def test_repair_already_stable_stays_stable():
    """If the object is already stable, the repair must keep it stable."""
    pap = _make_stable_pap()
    world = _world_with_one(pap)

    assert stability(pap, _identity()).ok, "fixture must start stable"

    result_tf = suggest_transform(world, "obj", {})
    res = stability(pap, result_tf)
    assert res.ok


# ---------------------------------------------------------------------------
# Test 4: collision-aware repair — greedy fallback still gives a stable transform
# ---------------------------------------------------------------------------
def test_repair_with_collision_obstacle_still_stable():
    """When sliding would collide with a wall, the solver (or greedy fallback)
    still returns a stability-valid transform."""
    world, obj_id = _world_with_obstacle()
    pap = world.get(obj_id).pap

    result_tf = suggest_transform(world, obj_id, {})

    res = stability(pap, result_tf)
    assert res.ok, (
        f"repair must produce stable transform even with obstacle; "
        f"margin={res.value_m:.4f}"
    )


# ---------------------------------------------------------------------------
# Test 5: movement penalty keeps repair small when already near-stable
# ---------------------------------------------------------------------------
def test_repair_minimal_movement_when_near_stable():
    """When the object is close to stable (CoM near the polygon edge but inside with
    sufficient margin), suggest_transform should not move it far from its initial position."""
    # CoM at x=0.1 inside a half=0.3 square footprint → margin 0.2, well stable.
    pap = PAP(
        asset_id="near_stable",
        geometry=Geometry(aabb=[0.3, 0.3, 0.5], obb=[0.3, 0.3, 0.5], volume_m3=0.045, convex_parts=1),
        physical=Physical(mass_kg=5.0, com=[0.1, 0.0, 0.3]),
        structural=Structural(support_footprint=_square_footprint(0.3)),
        semantics=Semantics(front=[0.0, 1.0, 0.0]),
    )
    world = _world_with_one(pap)

    initial_pos = np.asarray([0.0, 0.0, 0.0])
    result_tf = suggest_transform(world, "obj", {})
    result_pos = np.asarray(result_tf.pos[:2])

    # Should not move more than 0.5 m from the initial position.
    displacement = float(np.linalg.norm(result_pos - initial_pos[:2]))
    assert displacement < 0.5, f"excessive movement: {displacement:.3f} m"


# ---------------------------------------------------------------------------
# Test 6: yaw intent rotates the object
# ---------------------------------------------------------------------------
def test_repair_with_yaw_intent():
    """When intent specifies a target yaw, the returned quaternion should
    reflect a yaw rotation and still keep the object stable."""
    pap = _make_stable_pap()
    world = _world_with_one(pap)

    # Ask for 45° yaw.
    intent = {"target_yaw_deg": 45.0}
    result_tf = suggest_transform(world, "obj", intent)

    # Must still be stable.
    res = stability(pap, result_tf)
    assert res.ok

    # Quaternion should be non-identity (yaw changed).
    q = np.asarray(result_tf.quat)
    identity_q = np.array([0.0, 0.0, 0.0, 1.0])
    # The yaw-changed transform will have a different quat than identity.
    assert not np.allclose(q, identity_q, atol=0.01), "yaw intent should rotate the object"


# ---------------------------------------------------------------------------
# Test 7: greedy fallback works when SLSQP fails
# ---------------------------------------------------------------------------
def test_repair_greedy_fallback_is_stable():
    """Even if SLSQP fails (tested by monkeypatching the solver to always fail),
    the greedy fallback applies the stability gate's fix.translate and returns
    a stability-valid Transform."""
    import cortex.repair as repair_mod
    from scipy.optimize import OptimizeResult

    pap = _make_topple_pap()
    world = _world_with_one(pap)

    # Monkeypatch scipy.optimize.minimize to always return a failure.
    original_minimize = repair_mod.minimize

    def always_fail(*args, **kwargs):
        return OptimizeResult(success=False, x=np.zeros(3), fun=0.0,
                              message="monkeypatched failure")

    repair_mod.minimize = always_fail
    try:
        result_tf = suggest_transform(world, "obj", {})
    finally:
        repair_mod.minimize = original_minimize

    res = stability(pap, result_tf)
    assert res.ok, (
        f"greedy fallback must produce stable transform; margin={res.value_m:.4f}"
    )
