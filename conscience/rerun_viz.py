"""
The 3D conscience (Task B2) — render a Verdict to Rerun, fully headless.

This module turns a `Verdict` (+ the asset's `PAP` and its world `Transform`) into
a 3D picture: the asset bbox coloured by status, the centre-of-mass marker, the
support polygon on the floor, the gravity vector, and — when stability fails — a
*ghost* of the toppled candidate plus a *fix arrow* pointing the way back to safe.

It is a **pure consumer of the contract**. It computes no physics and never imports
anything from `cortex/`; every shape it draws is read straight out of the verdict
JSON, the PAP and the transform. Person A decides *what is true*; this module only
decides *how truth looks*.

Headless by construction
------------------------
We never spawn the viewer. `init_recording(path)` opens a `rr.RecordingStream`,
binds it to a `.rrd` file with `rec.save(path)`, and stamps the canonical-space
root with an explicit `rr.ViewCoordinates.RIGHT_HAND_Z_UP` (Z-up, right-handed,
metres — the canonical convention) so a silent handedness flip is caught the moment
the recording is opened.

Canonical space only
--------------------
Everything logged here is in canonical space (RH, Z-up, metres). The UE5 mirror /
cm conversion lives exclusively in `conscience.ue5.adapter`; the conscience renders
the same numbers the cortex reasoned over.
"""

from __future__ import annotations

from typing import Callable, Optional

import numpy as np
import rerun as rr

from contracts import PAP, GateResult, Transform, Verdict

# --------------------------------------------------------------------------- #
# Where everything lives in the entity tree. All under one canonical root so the
# single RIGHT_HAND_Z_UP view-coordinates governs the whole scene.
# --------------------------------------------------------------------------- #
ROOT = "world"
_BBOX = f"{ROOT}/bbox"
_COM = f"{ROOT}/com"
_SUPPORT = f"{ROOT}/support"
_GRAVITY = f"{ROOT}/gravity"
_GHOST = f"{ROOT}/ghost"
_FIX = f"{ROOT}/fix"

# Status palette (RGBA). Green = all hard gates pass and no soft cost; amber = soft
# violations only (renders, but flagged); red = a hard gate failed (commit blocked).
_GREEN = (40, 200, 80, 255)
_AMBER = (235, 170, 0, 255)
_RED = (220, 50, 50, 255)
_GHOST_GREY = (150, 150, 150, 120)
_COM_COLOR = (255, 80, 80, 255)
_SUPPORT_COLOR = (90, 160, 255, 255)
_GRAVITY_COLOR = (120, 120, 255, 255)
_FIX_COLOR = (60, 220, 220, 255)

# How tall (metres) to draw the gravity arrow above the asset, and its origin lift.
_GRAVITY_LEN = 1.0

# Soft-cost above which the bbox reads amber instead of green. A passing verdict can
# carry a tiny residual soft cost (e.g. fixtures.VERDICT_REPAIRED at 0.12) and should
# still read "clean / green"; only a *meaningful* soft violation warrants the amber flag.
_SOFT_AMBER_THRESHOLD = 1.0

LogFn = Callable[..., None]


# --------------------------------------------------------------------------- #
# Recording lifecycle
# --------------------------------------------------------------------------- #
def init_recording(
    path: str,
    *,
    app_id: str = "plumb-conscience",
    log_fn: Optional[LogFn] = None,
) -> rr.RecordingStream:
    """
    Open a headless Rerun recording that streams to `path` (a `.rrd` file).

    Sets the canonical-space view coordinates (`RIGHT_HAND_Z_UP`) on the root so a
    handedness flip is impossible to miss, and returns the `RecordingStream` for
    `draw_verdict` to log into. The viewer is NEVER spawned.

    `log_fn` is a seam for tests: a thin logging spy can be passed to capture what
    would be logged without touching the recording. It defaults to `rec.log`.
    """
    rec = rr.RecordingStream(app_id)
    rec.save(path)
    log = log_fn if log_fn is not None else rec.log
    # Static: the convention holds for all of time, not a single frame.
    log(ROOT, rr.ViewCoordinates.RIGHT_HAND_Z_UP, static=True)
    return rec


# --------------------------------------------------------------------------- #
# Maths helpers (canonical space only — no cortex, no physics)
# --------------------------------------------------------------------------- #
def _quat_to_matrix(quat) -> np.ndarray:
    """Rotation matrix from a canonical [x, y, z, w] quaternion."""
    x, y, z, w = (float(v) for v in quat)
    n = (x * x + y * y + z * z + w * w) ** 0.5
    if n == 0:
        return np.eye(3)
    x, y, z, w = x / n, y / n, z / n, w / n
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w),     2 * (x * z + y * w)],
        [2 * (x * y + z * w),     1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w),     2 * (y * z + x * w),     1 - 2 * (x * x + y * y)],
    ])


def _apply_transform(t: Transform, local_point) -> np.ndarray:
    """Map a point from the asset's local frame into world (canonical) space."""
    R = _quat_to_matrix(t.quat)
    s = np.asarray(t.scale, dtype=float)
    p = np.asarray(local_point, dtype=float)
    return np.asarray(t.pos, dtype=float) + R @ (s * p)


def _half_extents(pap: PAP) -> np.ndarray:
    """The bbox half-extents (OBB preferred, AABB fallback, then a tiny default)."""
    he = pap.geometry.obb or pap.geometry.aabb
    if not he:
        return np.array([0.1, 0.1, 0.1])
    return np.asarray(he, dtype=float)


def _support_polygon(pap: PAP, t: Transform) -> list[list[float]]:
    """
    The closed support polygon on the floor (canonical z = 0), world-transformed.

    Prefers the baked `structural.support_footprint` (the hull of ground-contact
    points). When the PAP carries none, falls back to the four bottom corners of the
    OBB projected to the floor so there is always a polygon to draw — the conscience
    should never go silent just because a prior is missing.
    """
    he = _half_extents(pap)
    footprint = pap.structural.support_footprint
    if footprint:
        local = [[float(p[0]), float(p[1]), 0.0] for p in footprint]
    else:
        hx, hy = float(he[0]), float(he[1])
        local = [[-hx, -hy, 0.0], [hx, -hy, 0.0], [hx, hy, 0.0], [-hx, hy, 0.0]]
    world = [_apply_transform(t, p).tolist() for p in local]
    if world and world[0] != world[-1]:
        world.append(world[0])  # close the loop for the line strip
    return world


# --------------------------------------------------------------------------- #
# Status -> colour, read from the Verdict JSON alone.
# --------------------------------------------------------------------------- #
def _status_color(verdict: Verdict):
    """Red on any hard fail, amber on a meaningful soft cost, green when clean."""
    if not verdict.ok:
        return _RED
    if verdict.soft_cost > _SOFT_AMBER_THRESHOLD:
        return _AMBER
    return _GREEN


def _first_fix(verdict: Verdict) -> Optional[GateResult]:
    """The first gate that carries a fix vector, if any."""
    for g in verdict.gates:
        if g.fix is not None:
            return g
    return None


# --------------------------------------------------------------------------- #
# The render
# --------------------------------------------------------------------------- #
def draw_verdict(
    rec: rr.RecordingStream,
    pap: PAP,
    transform: Transform,
    verdict: Verdict,
    *,
    log_fn: Optional[LogFn] = None,
) -> None:
    """
    Draw one Verdict into the recording — the whole picture from the contract alone.

    Logged entities (all in canonical RH Z-up metres):
      * ``world/bbox``    — the asset OBB as `Boxes3D`, coloured green (pass) /
                            amber (soft-only) / red (hard fail) by the verdict status.
      * ``world/com``     — the centre of mass as a `Points3D` marker, world-transformed.
      * ``world/support`` — the support polygon on the floor as `LineStrips3D`.
      * ``world/gravity`` — the gravity vector (-Z) as an `Arrows3D`.
      * ``world/ghost``   — (stability fail only) a translucent bbox at the toppled
                            candidate, nudged by the fix delta so it reads as "where it
                            would have ended up".
      * ``world/fix``     — (only when a gate carries a fix) the "shift toward centre"
                            arrow = ``gate.fix.translate``.

    Pure consumer: no physics is computed and `cortex` is never imported.
    """
    log = log_fn if log_fn is not None else rec.log

    he = _half_extents(pap)
    center = np.asarray(transform.pos, dtype=float)
    color = _status_color(verdict)

    # 1. The asset bbox, coloured by status.
    log(_BBOX, rr.Boxes3D(
        centers=[center.tolist()],
        half_sizes=[he.tolist()],
        quaternions=[rr.Quaternion(xyzw=list(transform.quat))],
        colors=[color],
        labels=[f"{pap.asset_id}"],
    ))

    # 2. The centre of mass marker (world-transformed from the local CoM).
    com_world = _apply_transform(transform, pap.physical.com)
    log(_COM, rr.Points3D([com_world.tolist()], colors=[_COM_COLOR], radii=[0.03]))

    # 3. The support polygon on the floor.
    log(_SUPPORT, rr.LineStrips3D(
        [_support_polygon(pap, transform)], colors=[_SUPPORT_COLOR], radii=[0.005],
    ))

    # 4. Gravity (-Z), originating above the asset so it reads downward through it.
    grav_origin = (center + np.array([0.0, 0.0, float(he[2]) + _GRAVITY_LEN])).tolist()
    log(_GRAVITY, rr.Arrows3D(
        vectors=[[0.0, 0.0, -_GRAVITY_LEN]], origins=[grav_origin],
        colors=[_GRAVITY_COLOR], labels=["g"],
    ))

    # 5/6. On a fix (stability fail carries the topple recovery): ghost + fix arrow.
    fix_gate = _first_fix(verdict)
    if fix_gate is not None:
        translate = np.asarray(fix_gate.fix.translate, dtype=float)

        # Ghost bbox: the rejected candidate, offset OPPOSITE the fix (where it sat
        # before the suggested nudge) and dropped low to read as "toppled".
        ghost_center = (center - translate).tolist()
        log(_GHOST, rr.Boxes3D(
            centers=[ghost_center],
            half_sizes=[he.tolist()],
            colors=[_GHOST_GREY],
            labels=["toppled candidate"],
        ))

        # Fix arrow: the "shift toward centre" vector, rooted at the asset.
        log(_FIX, rr.Arrows3D(
            vectors=[translate.tolist()],
            origins=[center.tolist()],
            colors=[_FIX_COLOR],
            labels=[f"fix +{np.linalg.norm(translate) * 100:.0f}cm"],
        ))
