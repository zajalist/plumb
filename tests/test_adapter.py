"""
Golden round-trip tests for the canonical<->UE5 coordinate adapter (Task B1).

This is the §17.5 proof: the negate-X mirror + scale boundary, exercised so that a
silent handedness / winding / cm<->m bug can never reach the demo. If any golden
test here fails, `golden_roundtrip_ok()` must report False and the demo falls back
to commit-once / Rerun-only (spec §17.1).

Canonical: right-handed, Z-up, metres.   UE5: left-handed, Z-up, centimetres.
"""

from __future__ import annotations

import numpy as np

from contracts import Transform
from conscience.ue5 import adapter


# --------------------------------------------------------------------------- #
# Matrix sanity
# --------------------------------------------------------------------------- #
def test_matrix_is_inverse_of_itself_numeric_identity():
    M = adapter.M_CANON_TO_UE5
    Minv = adapter.M_UE5_TO_CANON
    assert M.shape == (4, 4)
    assert Minv.shape == (4, 4)
    np.testing.assert_allclose(M @ Minv, np.eye(4), atol=1e-12)
    np.testing.assert_allclose(Minv @ M, np.eye(4), atol=1e-12)


def test_matrix_is_a_mirror_negative_determinant():
    # A handedness flip means the 3x3 linear part has negative determinant.
    linear = adapter.M_CANON_TO_UE5[:3, :3]
    assert np.linalg.det(linear) < 0


# --------------------------------------------------------------------------- #
# Known point mapping (the spec's concrete example)
# --------------------------------------------------------------------------- #
def test_known_point_canon_to_ue5():
    # [1,2,3] m -> [-100,200,300] cm : negate-X + scale x100.
    assert adapter.canon_to_ue5_point([1.0, 2.0, 3.0]) == [-100.0, 200.0, 300.0]


def test_known_point_ue5_to_canon():
    assert adapter.ue5_to_canon_point([-100.0, 200.0, 300.0]) == [1.0, 2.0, 3.0]


def test_point_round_trip_identity():
    for p in ([1.0, 2.0, 3.0], [-4.2, 0.0, 9.9], [0.0, 0.0, 0.0]):
        back = adapter.ue5_to_canon_point(adapter.canon_to_ue5_point(p))
        np.testing.assert_allclose(back, p, atol=1e-12)


# --------------------------------------------------------------------------- #
# Golden round-trip: 8 OBB corners of a known box survive canon->UE5->canon.
# --------------------------------------------------------------------------- #
def test_golden_obb_corners_round_trip():
    # Half-extents of the bronze figure proxy (metres), centred at an offset.
    center = np.array([0.30, -0.20, 0.75])
    he = np.array([0.15, 0.15, 0.75])
    signs = np.array([[sx, sy, sz] for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)])
    corners = center + signs * he  # 8 corners

    out = []
    for c in corners:
        ue5 = adapter.canon_to_ue5_point(list(c))
        back = adapter.ue5_to_canon_point(ue5)
        out.append(back)
    np.testing.assert_allclose(np.array(out), corners, atol=1e-12)


# --------------------------------------------------------------------------- #
# Quaternion: mirror is NOT a pass-through; round-trip survives up to sign.
# --------------------------------------------------------------------------- #
def _rand_unit_quat(rng) -> list[float]:
    q = rng.standard_normal(4)
    q = q / np.linalg.norm(q)
    return q.tolist()


def _quat_to_R(q) -> np.ndarray:
    x, y, z, w = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w),     2 * (x * z + y * w)],
        [2 * (x * y + z * w),     1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w),     2 * (y * z + x * w),     1 - 2 * (x * x + y * y)],
    ])


def test_quat_is_not_a_passthrough():
    # A rotation about Z must change under the X-mirror (sense reverses).
    q = [0.0, 0.0, np.sin(0.6), np.cos(0.6)]  # 1.2 rad about +Z
    out = adapter.canon_to_ue5_quat(q)
    assert not np.allclose(out, q, atol=1e-9)


def test_quat_round_trip_up_to_sign():
    rng = np.random.default_rng(17)
    for _ in range(20):
        q = _rand_unit_quat(rng)
        back = adapter.ue5_to_canon_quat(adapter.canon_to_ue5_quat(q))
        # q and -q are the same rotation: compare rotation matrices.
        np.testing.assert_allclose(_quat_to_R(back), _quat_to_R(q), atol=1e-10)


def test_quat_mirror_matches_matrix_conjugation():
    # The mirrored quaternion must equal R' = M R M (M = diag(-1,1,1)) as a rotation.
    rng = np.random.default_rng(99)
    M = np.diag([-1.0, 1.0, 1.0])
    for _ in range(20):
        q = _rand_unit_quat(rng)
        mirrored = adapter.canon_to_ue5_quat(q)
        expected_R = M @ _quat_to_R(q) @ M
        np.testing.assert_allclose(_quat_to_R(mirrored), expected_R, atol=1e-10)


def test_quat_path_commutes_with_point_mirror_on_a_rotated_point():
    # Directional pin: the quaternion path must agree with the POINT path on a
    # concrete rotated point. Rotating a local point m, then mirroring it through
    # the negate-X point mirror P, must equal mirroring m first and then rotating
    # by the MIRRORED quaternion:
    #
    #     P @ (R(q) @ m)  ==  R(canon_to_ue5_quat(q)) @ (P @ m).
    #
    # The existing round-trip / conjugation tests use the same M on both sides and
    # cannot catch a wrong mirror axis; tying the rotated-point image through the
    # independent point mirror P does. (P matches adapter's negate-X point map.)
    rng = np.random.default_rng(2024)
    P = np.diag([-1.0, 1.0, 1.0])
    for _ in range(50):
        q = _rand_unit_quat(rng)
        m = rng.standard_normal(3)
        lhs = P @ (_quat_to_R(q) @ m)
        rhs = _quat_to_R(adapter.canon_to_ue5_quat(q)) @ (P @ m)
        np.testing.assert_allclose(lhs, rhs, atol=1e-10)


# --------------------------------------------------------------------------- #
# Winding / normals: a face normal points OUTWARD after a full round-trip.
# --------------------------------------------------------------------------- #
def test_reflip_winding_reverses_triangle_order():
    faces = [(0, 1, 2), (3, 4, 5)]
    flipped = adapter.reflip_winding(faces)
    assert flipped == [(0, 2, 1), (3, 5, 4)]
    # involution: applying twice restores the original.
    assert adapter.reflip_winding(flipped) == faces


def test_normal_points_outward_after_round_trip():
    # One outward-facing triangle of a box (the +X face), CCW in canonical RH space.
    # Outward normal in canonical space is +X.
    v0 = np.array([1.0, -1.0, -1.0])
    v1 = np.array([1.0, 1.0, -1.0])
    v2 = np.array([1.0, 1.0, 1.0])
    centroid = np.array([0.0, 0.0, 0.0])

    def normal(a, b, c):
        n = np.cross(b - a, c - a)
        return n / np.linalg.norm(n)

    # Sanity: in canonical space this winding gives an outward (+X) normal.
    n_canon = normal(v0, v1, v2)
    assert np.dot(n_canon, v0 - centroid) > 0

    # Move verts to UE5 WITHOUT re-flipping winding -> normal points INWARD (the bug).
    u0 = np.array(adapter.canon_to_ue5_point(v0.tolist()))
    u1 = np.array(adapter.canon_to_ue5_point(v1.tolist()))
    u2 = np.array(adapter.canon_to_ue5_point(v2.tolist()))
    uc = np.array(adapter.canon_to_ue5_point(centroid.tolist()))
    n_bug = normal(u0, u1, u2)
    assert np.dot(n_bug, u0 - uc) < 0  # silently inward: the winding bug

    # Re-flip the winding -> normal points OUTWARD again in UE5 space.
    (a, b, c), = adapter.reflip_winding([(0, 1, 2)])
    verts = [u0, u1, u2]
    n_fixed = normal(verts[a], verts[b], verts[c])
    assert np.dot(n_fixed, verts[a] - uc) > 0


# --------------------------------------------------------------------------- #
# Transform round-trip on the contract Transform.
# --------------------------------------------------------------------------- #
def test_transform_round_trip():
    t = Transform(pos=[1.0, 2.0, 3.0], quat=[0.0, 0.0, np.sin(0.5), np.cos(0.5)], scale=[1.0, 2.0, 3.0])
    ue5 = adapter.canon_to_ue5_transform(t)
    assert ue5.pos == [-100.0, 200.0, 300.0]
    assert ue5.scale == [1.0, 2.0, 3.0]  # scale is dimensionless; unchanged

    back = adapter.ue5_to_canon_transform(ue5)
    np.testing.assert_allclose(back.pos, t.pos, atol=1e-12)
    np.testing.assert_allclose(back.scale, t.scale, atol=1e-12)
    np.testing.assert_allclose(_quat_to_R(back.quat), _quat_to_R(t.quat), atol=1e-10)


def test_transform_default_identity_quat_round_trips():
    t = Transform(pos=[0.0, 0.0, 0.5])  # default quat [0,0,0,1], scale [1,1,1]
    back = adapter.ue5_to_canon_transform(adapter.canon_to_ue5_transform(t))
    np.testing.assert_allclose(back.pos, t.pos, atol=1e-12)
    np.testing.assert_allclose(back.quat, t.quat, atol=1e-12)


# --------------------------------------------------------------------------- #
# The fallback flag (spec §17.1): golden_roundtrip_ok() gates the live demo.
# --------------------------------------------------------------------------- #
def test_golden_roundtrip_ok_is_true_when_adapter_is_sound():
    assert adapter.golden_roundtrip_ok() is True
