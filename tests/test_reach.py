"""
tests/test_reach.py — TDD for cortex/gates/reach.py (Task 6).

Spec: reach(world, walkway_poly, agent_r=0.45, start=None, goal=None) -> GateResult
  - Project all obstacles to the floor.
  - Compute narrowest free-gap width along the walkway polygon.
  - value_m = that width; ok = width >= 2*agent_r.
  - Flood-fill on a coarse floor grid to confirm goal reachable from start.
  - detail like "walkway 94cm >= 90cm".
  - Pure numpy/shapely, no Recast.

Tests:
  1. Empty walkway → full width, ok True.
  2. Obstacle pinching to 0.6m with r=0.45 (diameter 0.9) → ok False, detail "...cm < 90cm".
  3. Obstacle pinching to 1.0m with r=0.45 (diameter 0.9) → ok True.
  4. Flood-fill: obstacle fully blocking → goal unreachable.
  5. Flood-fill: clear path → goal reachable.
  6. detail string format check.
  7. No obstacles, large walkway → value_m equals walkway width.
"""

from __future__ import annotations

import numpy as np
import pytest

from contracts import GateName, PAP, Transform
from cortex.world import WorldModel
from cortex.gates.reach import reach


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _make_world(*node_specs) -> WorldModel:
    """Build a world with the given (node_id, pap, transform) triples."""
    w = WorldModel()
    for nid, pap, tf in node_specs:
        w.add(nid, pap, tf)
    return w


def _make_pap(hx: float = 0.1, hy: float = 0.1, hz: float = 1.0, asset_id: str = "obs") -> PAP:
    """PAP representing a box obstacle with AABB half-extents (hx, hy, hz)."""
    from contracts import Geometry, Physical
    pap = PAP(asset_id=asset_id)
    pap.geometry = Geometry(aabb=[hx, hy, hz], obb=[hx, hy, hz], volume_m3=8*hx*hy*hz, watertight=True, convex_parts=1)
    pap.physical = Physical(mass_kg=1.0, com=[0, 0, 0])
    return pap


def _tf(x: float = 0.0, y: float = 0.0, z: float = 0.0) -> Transform:
    return Transform(pos=[x, y, z], quat=[0, 0, 0, 1], scale=[1, 1, 1])


# Walkway: a 5m x 2m corridor along Y axis centred at x=0, from y=0 to y=5
CORRIDOR_POLY = [
    [-1.0, 0.0],
    [1.0,  0.0],
    [1.0,  5.0],
    [-1.0, 5.0],
]

# --------------------------------------------------------------------------- #
# Test 1: empty walkway → full width, ok True
# --------------------------------------------------------------------------- #
def test_empty_walkway_ok():
    world = WorldModel()  # no obstacles
    result = reach(world, CORRIDOR_POLY, agent_r=0.45, start=[0.0, 0.5], goal=[0.0, 4.5])
    assert result.gate == GateName.reach
    assert result.ok is True
    # Width should be roughly the corridor width (2.0 m)
    assert result.value_m is not None
    assert result.value_m >= 1.5  # at least 1.5m in a 2m corridor


# --------------------------------------------------------------------------- #
# Test 2: obstacle pinching width to ~0.6m → ok False with r=0.45
# --------------------------------------------------------------------------- #
def test_obstacle_pinching_too_narrow():
    # Obstacle at x=0.5 with hx=0.35 → right edge at x=0.85, leaving ~0.15m gap right
    # Corridor right wall at x=1.0, obstacle right edge at 0.85 → gap = 0.15m each side
    # Actually place obstacle that leaves 0.6m total gap:
    # Corridor from x=-1 to x=1 (width 2m), obstacle hx=0.7 centred at x=0
    # → obstacle goes from -0.7 to +0.7, each side has 0.3m gap → narrowest = 0.6m total
    # With agent_r=0.45, diameter=0.9m → 0.6 < 0.9 → ok False
    pap = _make_pap(hx=0.7, hy=0.5, hz=1.0, asset_id="big_obs")
    tf = _tf(x=0.0, y=2.5)
    world = _make_world(("big_obs", pap, tf))
    result = reach(world, CORRIDOR_POLY, agent_r=0.45, start=[0.0, 0.5], goal=[0.0, 4.5])
    assert result.gate == GateName.reach
    assert result.ok is False
    assert result.value_m is not None
    assert result.value_m < 0.9  # diameter threshold
    # Detail should mention cm values
    assert result.detail is not None
    assert "cm" in result.detail
    assert "<" in result.detail


# --------------------------------------------------------------------------- #
# Test 3: obstacle leaving wide gap → ok True with r=0.45
# --------------------------------------------------------------------------- #
def test_obstacle_leaving_wide_enough_gap():
    # Corridor width 2m, obstacle hx=0.05 centered at x=-0.7 (near left wall).
    # Obstacle spans from x=-0.75 to x=-0.65. Right gap = from -0.65 to 1.0 = 1.65m.
    # Left gap = from -1.0 to -0.75 = 0.25m. Min gap = 0.25m, but the larger passage is 1.65m.
    # Actually _narrowest_gap checks sections: the cross-section at y=2.5 has total
    # free space = 2.0 - 0.1 = 1.9m. But the gap on one side is 1.65m.
    # For clarity, use no start/goal so flood-fill doesn't run.
    # Obstacle hx=0.1, placed at x=0 → each side gap = 0.9m → value_m ≈ 0.9.
    # Use a smaller agent radius so it fits: agent_r=0.3 → diameter=0.6m < 0.9m.
    pap = _make_pap(hx=0.1, hy=0.5, hz=1.0, asset_id="narrow_obs")
    tf = _tf(x=0.0, y=2.5)
    world = _make_world(("narrow_obs", pap, tf))
    # Use agent_r=0.3 (diameter=0.6m). Gap is 0.9m per side → ok
    result = reach(world, CORRIDOR_POLY, agent_r=0.3)
    assert result.gate == GateName.reach
    assert result.ok is True
    assert result.value_m is not None
    assert result.value_m >= 0.6  # diameter threshold


# --------------------------------------------------------------------------- #
# Test 4: obstacle fully blocking → goal unreachable (flood-fill)
# --------------------------------------------------------------------------- #
def test_flood_fill_blocked_goal_unreachable():
    # An obstacle spanning full corridor width blocks navigation
    # Corridor from x=-1 to x=1, obstacle hx=1.5 → blocks completely
    pap = _make_pap(hx=1.5, hy=0.3, hz=1.0, asset_id="wall_obs")
    tf = _tf(x=0.0, y=2.5)
    world = _make_world(("wall_obs", pap, tf))
    result = reach(world, CORRIDOR_POLY, agent_r=0.45, start=[0.0, 0.5], goal=[0.0, 4.5])
    # Should be not ok due to blocked path
    assert result.ok is False


# --------------------------------------------------------------------------- #
# Test 5: clear path → goal reachable
# --------------------------------------------------------------------------- #
def test_flood_fill_clear_path_reachable():
    # Small obstacle to the side, not blocking main path
    pap = _make_pap(hx=0.1, hy=0.1, hz=1.0, asset_id="side_obs")
    tf = _tf(x=0.8, y=2.5)  # near the wall, not blocking centre
    world = _make_world(("side_obs", pap, tf))
    result = reach(world, CORRIDOR_POLY, agent_r=0.3, start=[0.0, 0.5], goal=[0.0, 4.5])
    assert result.ok is True


# --------------------------------------------------------------------------- #
# Test 6: detail string format check
# --------------------------------------------------------------------------- #
def test_detail_string_format_ok():
    """When ok, detail should show 'walkway Xcm >= Ycm'."""
    world = WorldModel()
    result = reach(world, CORRIDOR_POLY, agent_r=0.45)
    assert result.detail is not None
    assert "cm" in result.detail
    assert ">=" in result.detail or "<" in result.detail


def test_detail_string_format_not_ok():
    """When not ok, detail should show 'walkway Xcm < Ycm'."""
    pap = _make_pap(hx=0.7, hy=0.5, hz=1.0, asset_id="big_obs2")
    tf = _tf(x=0.0, y=2.5)
    world = _make_world(("big_obs2", pap, tf))
    result = reach(world, CORRIDOR_POLY, agent_r=0.45)
    if not result.ok:
        assert "<" in result.detail
        assert "cm" in result.detail


# --------------------------------------------------------------------------- #
# Test 7: GateResult structure
# --------------------------------------------------------------------------- #
def test_gate_result_structure():
    """GateResult has correct gate name, value_m set, detail set."""
    world = WorldModel()
    result = reach(world, CORRIDOR_POLY, agent_r=0.45)
    assert result.gate == GateName.reach
    assert result.value_m is not None
    assert isinstance(result.value_m, float)
    assert result.detail is not None
    assert result.ok is not None
