"""
Tests for cortex/gates/stability.py (Task 4) — the Stability gate (THE BET).

The gate projects the world centre-of-mass straight down (the plumb line) onto the
floor and measures the signed margin from that point to the support polygon boundary:
positive inside, negative outside. ``ok`` iff margin >= STABILITY_MARGIN_M. On fail it
hands back a horizontal ``fix.translate`` that walks the CoM back toward the polygon
centre far enough to restore the margin — applying it must flip the verdict to ok.

The headline proof is the bronze-figure fixture from T3 (genuinely top-heavy, CoM high
on the Z axis) hung over a pedestal edge: the plumb CoM lands ~7 cm outside the contact
footprint, so the margin reproduces the demo number ≈ −0.07 m.

Deterministic trimesh primitives only (tests/helpers.py). Pure numpy/shapely.
"""

from __future__ import annotations

import math

import numpy as np

from contracts import PAP, FixVector, GateName, GateResult, Geometry, Physical, Structural, Transform
from cortex.bake.physical import bake_physical
from cortex.gates.stability import (
    STABILITY_MARGIN_M,
    stability,
    support_polygon,
)
from tests.helpers import two_part_topheavy


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _square_footprint(half: float, center=(0.0, 0.0)) -> list[list[float]]:
    """A square contact footprint of half-extent ``half`` centred at ``center``."""
    cx, cy = center
    return [
        [cx - half, cy - half],
        [cx + half, cy - half],
        [cx + half, cy + half],
        [cx - half, cy + half],
    ]


def _pap_with_footprint(com, footprint, aabb=(0.2, 0.2, 0.4)) -> PAP:
    """A minimal PAP carrying just the CoM and an authored support footprint."""
    return PAP(
        asset_id="fixture",
        geometry=Geometry(aabb=list(aabb), obb=list(aabb), volume_m3=1.0, convex_parts=1),
        physical=Physical(mass_kg=1.0, com=list(com)),
        structural=Structural(support_footprint=footprint),
    )


def _identity() -> Transform:
    return Transform(pos=[0.0, 0.0, 0.0])


# --------------------------------------------------------------------------- #
# support_polygon
# --------------------------------------------------------------------------- #
def test_support_polygon_uses_authored_footprint():
    """An authored structural.support_footprint wins, projected to world XY."""
    pap = _pap_with_footprint(com=[0, 0, 0.5], footprint=_square_footprint(0.2))
    poly = support_polygon(pap, _identity())
    pts = np.asarray(poly, dtype=float)
    assert pts.shape[1] == 2
    # Square half-extent 0.2 → spans [-0.2, 0.2] in both axes.
    assert math.isclose(pts[:, 0].min(), -0.2, abs_tol=1e-9)
    assert math.isclose(pts[:, 0].max(), 0.2, abs_tol=1e-9)


def test_support_polygon_rotates_with_transform_but_stays_world_anchored():
    """The footprint is the world contact patch: transform rotation orients it, but the
    body's *translation* slides the CoM over a stationary base (so a fix can flip the
    verdict). A 90° yaw swaps the x/y half-extents of a non-square footprint."""
    # Non-square footprint: half 0.3 in x, 0.1 in y.
    fp = [[-0.3, -0.1], [0.3, -0.1], [0.3, 0.1], [-0.3, 0.1]]
    pap = _pap_with_footprint(com=[0, 0, 0.5], footprint=fp)
    yaw90 = Transform(pos=[5.0, 7.0, 0.0], quat=[0.0, 0.0, math.sqrt(0.5), math.sqrt(0.5)])
    poly = support_polygon(pap, yaw90)
    pts = np.asarray(poly, dtype=float)
    # Rotation applied (x/y extents swap), translation NOT applied (base stays anchored).
    assert math.isclose(pts[:, 0].max(), 0.1, abs_tol=1e-6)
    assert math.isclose(pts[:, 1].max(), 0.3, abs_tol=1e-6)


def test_support_polygon_falls_back_to_aabb_when_no_footprint():
    """No authored footprint → derive a footprint from the asset's bbox half-extents."""
    pap = PAP(
        asset_id="boxish",
        geometry=Geometry(aabb=[0.3, 0.15, 0.5], obb=[0.3, 0.15, 0.5], volume_m3=1.0, convex_parts=1),
        physical=Physical(mass_kg=1.0, com=[0, 0, 0.5]),
    )
    poly = support_polygon(pap, _identity())
    pts = np.asarray(poly, dtype=float)
    assert math.isclose(pts[:, 0].max(), 0.3, abs_tol=1e-9)
    assert math.isclose(pts[:, 1].max(), 0.15, abs_tol=1e-9)


# --------------------------------------------------------------------------- #
# stability — sign, magnitude, ok
# --------------------------------------------------------------------------- #
def test_centered_com_is_stable_positive_margin():
    """CoM centred over a square base → margin > 0, ok True."""
    pap = _pap_with_footprint(com=[0, 0, 0.5], footprint=_square_footprint(0.2))
    res = stability(pap, _identity())
    assert isinstance(res, GateResult)
    assert res.gate == GateName.stability
    assert res.value_m is not None and res.value_m > 0
    assert res.ok is True
    # Centred in a 0.4×0.4 base → distance to nearest edge is 0.2.
    assert math.isclose(res.value_m, 0.2, abs_tol=1e-6)
    assert res.fix is None


def test_margin_matches_hand_computed_value_on_unit_square():
    """A unit square base with CoM offset 0.3 in x → 0.5 − 0.3 = 0.2 to the near edge."""
    pap = _pap_with_footprint(com=[0.3, 0.0, 1.0], footprint=_square_footprint(0.5))
    res = stability(pap, _identity())
    assert math.isclose(res.value_m, 0.2, abs_tol=1e-6)
    assert res.ok is True


def test_com_past_edge_is_unstable_negative_margin():
    """CoM shoved past an edge → margin < 0, ok False, fix points back to centre."""
    # Footprint square spans x in [-0.2, 0.2]; CoM at x=0.5 → 0.3 outside the right edge.
    pap = _pap_with_footprint(com=[0.5, 0.0, 1.0], footprint=_square_footprint(0.2))
    res = stability(pap, _identity())
    assert res.value_m is not None and res.value_m < 0
    assert math.isclose(res.value_m, -0.3, abs_tol=1e-6)
    assert res.ok is False
    assert res.viz == "com_outside_polygon"
    assert res.detail is not None
    # Fix is a horizontal vector (z = 0) pointing back toward the polygon centre (−x).
    assert isinstance(res.fix, FixVector)
    assert res.fix.translate[0] < 0
    assert math.isclose(res.fix.translate[2], 0.0, abs_tol=1e-12)


def test_applying_fix_restores_stability():
    """Adding fix.translate to the asset position flips the verdict to ok."""
    pap = _pap_with_footprint(com=[0.5, 0.0, 1.0], footprint=_square_footprint(0.2))
    res = stability(pap, _identity())
    assert res.ok is False

    moved = Transform(pos=[float(t) for t in res.fix.translate])
    res2 = stability(pap, moved)
    assert res2.ok is True
    assert res2.value_m >= STABILITY_MARGIN_M


def test_margin_threshold_is_the_gate():
    """A CoM just inside the boundary but below STABILITY_MARGIN_M fails the gate."""
    # CoM 1 cm inside the edge: positive margin 0.01 < default 0.02 tolerance → not ok.
    pap = _pap_with_footprint(com=[0.19, 0.0, 1.0], footprint=_square_footprint(0.2))
    res = stability(pap, _identity())
    assert res.value_m is not None and res.value_m > 0
    assert math.isclose(res.value_m, 0.01, abs_tol=1e-6)
    assert res.ok is False  # positive but under the margin tolerance


def test_stability_is_deterministic():
    pap = _pap_with_footprint(com=[0.5, 0.0, 1.0], footprint=_square_footprint(0.2))
    a = stability(pap, _identity())
    b = stability(pap, _identity())
    assert a.value_m == b.value_m
    assert a.fix.translate == b.fix.translate


# --------------------------------------------------------------------------- #
# The demo: top-heavy bronze figure over a pedestal edge → margin ≈ −0.07
# --------------------------------------------------------------------------- #
def test_bronze_figure_at_pedestal_edge_reproduces_demo_margin():
    """The real top-heavy bake (CoM high on Z) overhanging its contact patch by ~7 cm."""
    parts, materials = two_part_topheavy()
    phys = bake_physical(parts, {0: materials["base"], 1: materials["body"]})
    # Genuinely top-heavy: density-weighted CoM is high on Z and centred in XY.
    assert phys.com[2] > 0.2

    # The figure hangs over a pedestal edge: its contact footprint (the base square,
    # half-extent 0.2) sits offset so the plumb CoM lands 7 cm beyond the near edge.
    # Footprint centred at x = −0.27 → right edge at −0.07; CoM projects to x = 0.
    footprint = _square_footprint(0.2, center=(-0.27, 0.0))
    pap = _pap_with_footprint(com=phys.com, footprint=footprint)

    res = stability(pap, _identity())
    assert res.ok is False
    assert math.isclose(res.value_m, -0.07, abs_tol=0.005)
    assert res.viz == "com_outside_polygon"
    # Applying the fix walks the figure back over its base.
    fixed = Transform(pos=[float(t) for t in res.fix.translate])
    assert stability(pap, fixed).ok is True
