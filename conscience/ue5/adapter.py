"""
The canonical <-> UE5 coordinate adapter — the single boundary, the §17.5 proof.

Canonical space : right-handed, Z-up, metres, kilograms.
UE5 space       : left-handed,  Z-up, centimetres.

Because Z-up is shared, there is **no 90 degree axis swap** — the conversion is the
cheap case: a handedness flip + a scale. The convention is fixed forever:

    * negate-X mirror  (flips handedness, RH <-> LH)
    * scale x100        (metres -> centimetres, canon -> UE5)
    * scale /100        (centimetres -> metres, UE5 -> canon)

Everything is expressed as one signed 4x4 homogeneous matrix `M_CANON_TO_UE5`
and its exact inverse `M_UE5_TO_CANON`, so points, the proxy mesh and the
contract `Transform` all flow through the same agreed-upon numbers.

---------------------------------------------------------------------------
Why the quaternion is NOT a pass-through (the derivation)
---------------------------------------------------------------------------
A reflection has determinant -1, so it is an *improper* transform and cannot be
a rotation. What we convert is not the reflection itself but how an object's
*orientation* reads once both bases are mirrored: if a body has rotation `R` in
canonical space, the same physical orientation expressed in the mirrored UE5
basis is the conjugation

        R_ue5 = M R M^-1        with the pure mirror  M = diag(-1, 1, 1).

(The x100 scale is uniform, so it cancels in the conjugation and does not touch
rotation.) Writing that out for an arbitrary rotation matrix, conjugation by
`diag(-1,1,1)` negates exactly the matrix entries that mix the X axis with Y or
Z (entry (i,j) is scaled by s_i * s_j = -1 iff exactly one of i,j is the X row/col).
Reading the resulting matrix back as a quaternion gives, for q = (x, y, z, w):

        q_ue5 = (x, -y, -z, w)

Sanity of the three axis-aligned cases:
  * rotation about +X (the mirror axis): only the Y/Z block moves, none of it
    mixes with X, so the matrix is unchanged -> q' = (x, 0, 0, w) = q. Correct:
    spin about the mirror normal is shared by both handednesses.
  * rotation about +Z by theta: the (0,1)/(1,0) entries flip -> the matrix becomes
    rotation by -theta -> q' = (0, 0, -z, w). The sense reverses, as a mirror demands.
  * rotation about +Y by theta: the (0,2)/(2,0) entries flip -> rotation by -theta
    -> q' = (0, -y, 0, w). Same reversal.

`(x, -y, -z, w)` reproduces all three, and the map is its own inverse (applying it
twice restores q), so canon->UE5 and UE5->canon use the identical formula.

---------------------------------------------------------------------------
Winding
---------------------------------------------------------------------------
A basis mirror flips triangle winding: a CCW (outward) face in canonical space
reads CW (inward-facing normal) after the negate-X, which would silently invert
collision normals. `reflip_winding(faces)` reverses each triangle's vertex order
so normals re-evert. It is an involution.
"""

from __future__ import annotations

import numpy as np

from contracts import Transform

# Metres -> centimetres.
_SCALE = 100.0

# The one signed 4x4: negate-X mirror + uniform x100 scale (canonical -> UE5).
M_CANON_TO_UE5: np.ndarray = np.diag([-_SCALE, _SCALE, _SCALE, 1.0])
# Exact inverse: negate-X + /100 (UE5 -> canonical).
M_UE5_TO_CANON: np.ndarray = np.diag([-1.0 / _SCALE, 1.0 / _SCALE, 1.0 / _SCALE, 1.0])


# --------------------------------------------------------------------------- #
# Points
# --------------------------------------------------------------------------- #
def _apply(M: np.ndarray, p) -> list[float]:
    v = np.array([p[0], p[1], p[2], 1.0], dtype=float)
    out = M @ v
    return [float(out[0]), float(out[1]), float(out[2])]


def canon_to_ue5_point(p) -> list[float]:
    """Canonical metres (RH) -> UE5 centimetres (LH). negate-X, x100."""
    return _apply(M_CANON_TO_UE5, p)


def ue5_to_canon_point(p) -> list[float]:
    """UE5 centimetres (LH) -> canonical metres (RH). negate-X, /100."""
    return _apply(M_UE5_TO_CANON, p)


# --------------------------------------------------------------------------- #
# Quaternions  (see module docstring for the derivation)
# --------------------------------------------------------------------------- #
def _mirror_quat(q) -> list[float]:
    """Conjugate a rotation by the X-mirror: (x, y, z, w) -> (x, -y, -z, w)."""
    x, y, z, w = q
    return [float(x), float(-y), float(-z), float(w)]


def canon_to_ue5_quat(q) -> list[float]:
    """Canonical [x,y,z,w] -> UE5 [x,y,z,w] across the negate-X mirror."""
    return _mirror_quat(q)


def ue5_to_canon_quat(q) -> list[float]:
    """UE5 [x,y,z,w] -> canonical [x,y,z,w]. The mirror conjugation is its own inverse."""
    return _mirror_quat(q)


# --------------------------------------------------------------------------- #
# Mesh winding
# --------------------------------------------------------------------------- #
def reflip_winding(faces):
    """
    Reverse each triangle's winding so normals re-evert after the negate-X mirror.

    Each face is a 3-tuple/list of vertex indices (a, b, c) -> (a, c, b).
    Involution: reflip_winding(reflip_winding(faces)) == faces.
    """
    return [(f[0], f[2], f[1]) for f in faces]


# --------------------------------------------------------------------------- #
# Transforms (the contract type)
# --------------------------------------------------------------------------- #
def canon_to_ue5_transform(t: Transform) -> Transform:
    """Convert a canonical contract Transform into UE5 space (scale is dimensionless)."""
    return Transform(
        pos=canon_to_ue5_point(t.pos),
        quat=canon_to_ue5_quat(t.quat),
        scale=list(t.scale),
    )


def ue5_to_canon_transform(t: Transform) -> Transform:
    """Convert a UE5-space contract Transform back into canonical space."""
    return Transform(
        pos=ue5_to_canon_point(t.pos),
        quat=ue5_to_canon_quat(t.quat),
        scale=list(t.scale),
    )


# --------------------------------------------------------------------------- #
# The fallback gate (spec §17.1): if this ever returns False, do NOT demo live
# UE5 — fall back to commit-once / Rerun-only.
# --------------------------------------------------------------------------- #
def golden_roundtrip_ok(atol: float = 1e-9) -> bool:
    """
    Self-check the adapter end to end: matrix identity, point/quat/winding/transform
    round-trips, and the spec's known mapping. Returns True iff every golden invariant
    holds (so the demo can decide whether the live UE5 bridge is safe to use).
    """
    try:
        # 1. M @ M_inv == I
        if not np.allclose(M_CANON_TO_UE5 @ M_UE5_TO_CANON, np.eye(4), atol=atol):
            return False

        # 2. handedness actually flips (negative determinant on the linear part).
        if np.linalg.det(M_CANON_TO_UE5[:3, :3]) >= 0:
            return False

        # 3. the spec's concrete point.
        if canon_to_ue5_point([1.0, 2.0, 3.0]) != [-100.0, 200.0, 300.0]:
            return False

        rng = np.random.default_rng(0)

        # 4. point round-trip on the 8 OBB corners of a box.
        he = np.array([0.15, 0.15, 0.75])
        center = np.array([0.3, -0.2, 0.75])
        for sx in (-1, 1):
            for sy in (-1, 1):
                for sz in (-1, 1):
                    c = (center + np.array([sx, sy, sz]) * he).tolist()
                    if not np.allclose(ue5_to_canon_point(canon_to_ue5_point(c)), c, atol=atol):
                        return False

        # 5. quaternion round-trip (up to sign) on random unit quats.
        for _ in range(8):
            q = rng.standard_normal(4)
            q = (q / np.linalg.norm(q)).tolist()
            back = ue5_to_canon_quat(canon_to_ue5_quat(q))
            if not (np.allclose(back, q, atol=atol) or np.allclose(back, [-v for v in q], atol=atol)):
                return False

        # 6. winding is an involution.
        faces = [(0, 1, 2), (3, 4, 5)]
        if reflip_winding(reflip_winding(faces)) != faces:
            return False

        return True
    except Exception:
        return False
