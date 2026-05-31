"""
cortex/gates/stability.py — the Stability gate (Task 4, THE BET).

A body topples when its centre of mass, dropped straight down under gravity (the
*plumb line*), lands outside the polygon where the body actually touches the ground.
This gate makes that a number:

  * :func:`support_polygon` projects the asset's ground-contact footprint into world
    XY at a given transform — the authored ``structural.support_footprint`` when present,
    else a rectangle derived from the asset's bounding-box half-extents (the best
    PAP-only stand-in for "the lowest convex part's hull projected to the floor").
  * :func:`stability` drops the world CoM to XY and returns the **signed margin** to
    that polygon's boundary: ``+`` inside (stable), ``−`` outside (toppling). The gate
    is ``ok`` iff the margin clears :data:`STABILITY_MARGIN_M`.

The support footprint is the patch where the body rests on a supporting surface (the
ground or a pedestal), so it is **world-anchored**: the transform's rotation and scale
orient it, but its *translation* slides the body's CoM over a stationary base. That is
what makes the repair work — the ``fix.translate`` walks the projected CoM back toward
the polygon's centroid far enough to restore the margin, and applying it (sliding the
body) flips the verdict to ok. The same signed margin is the cost function the solver
in Task 8 minimises, so this stays a pure, deterministic function of (pap, transform).

Canonical space everywhere: Z-up, right-handed, metres, kilograms. The plumb line is
−Z, so the support polygon and the CoM both project by dropping the Z coordinate.
"""

from __future__ import annotations

import numpy as np
from shapely.geometry import Point, Polygon

from contracts import FixVector, GateName, GateResult, Transform

# Required CoM-over-polygon clearance for a placement to count as stable (metres).
# 2 cm of margin keeps us off the knife-edge where float noise or a nudge topples it.
STABILITY_MARGIN_M = 0.02

# Extra slack baked into the repair so the fixed placement lands *strictly* past the
# threshold rather than exactly on it (where rounding could still read as failing).
_FIX_EPS = 1e-4


def support_polygon(pap, transform: Transform, anchored: bool = True) -> list[list[float]]:
    """World-XY contact footprint of ``pap`` placed at ``transform``.

    Uses the authored ``pap.structural.support_footprint`` (a 2D hull of ground-contact
    points in the asset's local frame) when it is present; otherwise derives an
    axis-aligned rectangle from the asset's bounding-box half-extents — the closest
    a PAP-only call can get to "the lowest convex part's hull projected to the floor".
    Each local point is lifted to 3D (z = 0), pushed through the transform, then projected
    back to XY by dropping Z.

    ``anchored`` (default) keeps the footprint at the origin — the *pedestal* model, where
    sliding the body moves its CoM over a stationary support (the gallery beat). With
    ``anchored=False`` the footprint **translates with the body** — the *free-standing*
    model, where an object rests on its own base wherever it sits (a tree on terrain);
    such a body topples only when tilt or slope carries its CoM off its own base.
    """
    local = _local_footprint(pap)
    world = _project_to_world_xy(local, transform, anchored=anchored)
    return [[float(x), float(y)] for x, y in world]


def stability(pap, transform: Transform, anchored: bool = True) -> GateResult:
    """Signed CoM-over-support-polygon margin for ``pap`` at ``transform``.

    Returns a :class:`GateResult` whose ``value_m`` is the margin (``+`` inside the
    support polygon, ``−`` outside) and whose ``ok`` is ``value_m >= STABILITY_MARGIN_M``.
    On failure it attaches a horizontal ``fix.translate`` pointing the projected CoM
    back toward the polygon centroid, scaled to restore the margin, plus a viz hint and
    a human ``detail`` string. Pure and deterministic — also the solver's cost function.

    ``anchored=False`` switches to the free-standing model (footprint co-moves with the
    body) — used for objects resting on a ground plane, e.g. forest trees on terrain.
    """
    poly = Polygon(support_polygon(pap, transform, anchored=anchored))
    com_xy = _world_com_xy(pap, transform)

    margin = _signed_margin(com_xy, poly)
    ok = margin >= STABILITY_MARGIN_M

    if ok:
        return GateResult(gate=GateName.stability, ok=True, value_m=float(margin))

    fix = _repair_translate(com_xy, poly, margin)
    return GateResult(
        gate=GateName.stability,
        ok=False,
        value_m=float(margin),
        fix=fix,
        viz="com_outside_polygon",
        detail=_detail(margin),
    )


# --------------------------------------------------------------------------- #
# Footprint construction
# --------------------------------------------------------------------------- #
def _local_footprint(pap) -> np.ndarray:
    """The asset-local 2D contact footprint as an ``(N, 2)`` array.

    Authored ``support_footprint`` wins; else a rectangle from the bbox half-extents.
    """
    authored = getattr(pap.structural, "support_footprint", None) or []
    if authored:
        return np.asarray(authored, dtype=float)[:, :2]
    return _bbox_rectangle(pap)


def _bbox_rectangle(pap) -> np.ndarray:
    """Axis-aligned footprint rectangle from the asset's bbox half-extents.

    Prefers the AABB (axis-aligned to the canonical frame); falls back to the OBB
    half-extents, then to a tiny unit patch so the polygon is never degenerate.
    """
    half = pap.geometry.aabb or pap.geometry.obb or [0.5, 0.5, 0.5]
    hx, hy = float(half[0]), float(half[1])
    if hx <= 0:
        hx = 0.5
    if hy <= 0:
        hy = 0.5
    return np.array(
        [[-hx, -hy], [hx, -hy], [hx, hy], [-hx, hy]],
        dtype=float,
    )


def _project_to_world_xy(
    local_xy: np.ndarray, transform: Transform, anchored: bool = True
) -> np.ndarray:
    """Orient the contact footprint into world XY through ``transform``.

    When ``anchored`` (the pedestal model), the transform's scale and rotation orient the
    footprint but its *translation* is deliberately NOT applied — sliding the body moves
    the CoM over a stationary base, which is what lets a ``fix`` restore stability. When
    not anchored (free-standing on a ground plane), the translation IS applied so the base
    co-moves with the body. Points are lifted to z = 0; the world Z is then dropped.
    """
    pts3 = np.column_stack([local_xy, np.zeros(len(local_xy))])
    world3 = _apply_transform(pts3, transform, translate=not anchored)
    return world3[:, :2]


# --------------------------------------------------------------------------- #
# CoM projection
# --------------------------------------------------------------------------- #
def _world_com_xy(pap, transform: Transform) -> np.ndarray:
    """World-XY projection of the asset's centre of mass under ``transform``."""
    com = np.asarray(pap.physical.com, dtype=float).reshape(1, 3)
    world = _apply_transform(com, transform)
    return world[0, :2]


# --------------------------------------------------------------------------- #
# Transform application (scale → rotate → translate)
# --------------------------------------------------------------------------- #
def _apply_transform(
    points: np.ndarray, transform: Transform, translate: bool = True
) -> np.ndarray:
    """Apply ``transform`` (scale, then rotate, then optionally translate) to points.

    ``points`` is ``(N, 3)``. When ``translate`` is False the position offset is skipped
    (used for the world-anchored support footprint, which only takes orientation/scale).
    """
    pts = np.asarray(points, dtype=float)
    scale = np.asarray(transform.scale, dtype=float)
    rot = _quat_to_matrix(transform.quat)
    out = (rot @ (pts * scale).T).T
    if translate:
        out = out + np.asarray(transform.pos, dtype=float)
    return out


def _quat_to_matrix(quat: list[float]) -> np.ndarray:
    """Rotation matrix from a normalised ``[x, y, z, w]`` quaternion."""
    x, y, z, w = (float(v) for v in quat)
    n = (x * x + y * y + z * z + w * w) ** 0.5
    if n == 0:
        return np.eye(3)
    x, y, z, w = x / n, y / n, z / n, w / n
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ],
        dtype=float,
    )


# --------------------------------------------------------------------------- #
# Signed margin + repair
# --------------------------------------------------------------------------- #
def _signed_margin(com_xy: np.ndarray, poly: Polygon) -> float:
    """Distance from the projected CoM to the polygon boundary: + inside, − outside.

    Magnitude is the nearest-edge distance either way; the sign is set by a
    point-in-polygon test (boundary points read as inside → 0 margin to the edge).
    """
    pt = Point(float(com_xy[0]), float(com_xy[1]))
    dist = pt.distance(poly.exterior)
    inside = poly.covers(pt)  # covers() includes the boundary
    return dist if inside else -dist


def _repair_translate(com_xy: np.ndarray, poly: Polygon, margin: float) -> FixVector:
    """Horizontal translate that restores the stability margin.

    Walks the asset (and so its CoM) from the failing projected CoM toward the polygon
    centroid by exactly enough to seat the CoM ``STABILITY_MARGIN_M`` inside the near
    edge. Direction is CoM → centroid; the rotation component is left untouched.
    """
    centroid = np.array([poly.centroid.x, poly.centroid.y], dtype=float)
    direction = centroid - com_xy
    norm = float(np.linalg.norm(direction))
    if norm == 0:
        # CoM sits on the centroid yet still fails (tiny/degenerate polygon): nudge +x.
        unit = np.array([1.0, 0.0])
    else:
        unit = direction / norm

    # Need to gain (STABILITY_MARGIN_M − margin) of clearance; margin is negative (or
    # below tolerance) here. Moving along `unit` toward the interior buys margin 1:1.
    travel = (STABILITY_MARGIN_M - margin) + _FIX_EPS
    delta = unit * travel
    return FixVector(translate=[float(delta[0]), float(delta[1]), 0.0])


def _detail(margin: float) -> str:
    """Human string, e.g. ``"CoM 7cm outside polygon"``."""
    cm = int(round(abs(margin) * 100))
    return f"CoM {cm}cm outside polygon"
