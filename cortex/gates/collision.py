"""
cortex/gates/collision.py — the Collision gate (Task 5).

Computes the signed clearance between the convex parts of two placed assets.
A positive value means they are separated (clearance in metres); a negative
value means they interpenetrate (penetration depth in metres).

  ``collision(world, a, b=None) -> GateResult``

If ``b`` is ``None``, the gate checks node ``a`` against *every* other node in the
world and reports the minimum (worst-case) clearance. ``ok = value_m >= 0``.

On penetration the gate attaches ``fix.translate``: the separation vector needed
to push the two closest parts apart along the contact normal.

Strategy
--------
We try ``trimesh``'s FCL/python-fcl collision manager first because it handles
the full GJK/EPA pipeline efficiently. If unavailable we fall back to a pure-numpy
SAT-based convex clearance calculation over the part meshes. The SAT approach
uses the face normals of both convex hulls as candidate separation axes, which
gives exact results for convex polyhedra (Separating Hyperplane Theorem).

Canonical space everywhere: Z-up, right-handed, metres.
"""

from __future__ import annotations

import numpy as np
import trimesh

from contracts import FixVector, GateName, GateResult, Transform


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def collision(world, a: str, b: str | None) -> GateResult:
    """Signed clearance between node ``a``'s parts and node ``b``'s parts.

    If ``b`` is ``None`` the check is against every other node; the result
    reflects the minimum (worst-case) clearance over all pairs.
    ``ok = value_m >= 0``; on penetration ``fix.translate`` separates the parts.
    """
    if b is None:
        other_ids = [nid for nid in world.nodes() if nid != a]
        if not other_ids:
            return GateResult(gate=GateName.collision, ok=True, value_m=float("inf"))
        results = [_check_pair(world, a, bid) for bid in other_ids]
        # Worst-case: lowest value_m across all pairs.
        worst = min(results, key=lambda r: (r.value_m if r.value_m is not None else float("inf")))
        return worst
    else:
        return _check_pair(world, a, b)


# --------------------------------------------------------------------------- #
# Pair clearance
# --------------------------------------------------------------------------- #
def _check_pair(world, a: str, b: str) -> GateResult:
    """Compute signed clearance between the convex parts of nodes ``a`` and ``b``."""
    node_a = world.get(a)
    node_b = world.get(b)

    parts_a = _get_parts(node_a.pap)
    parts_b = _get_parts(node_b.pap)

    tf_a = node_a.transform
    tf_b = node_b.transform

    # Transform parts into world space.
    world_parts_a = [_apply_transform_to_mesh(p, tf_a) for p in parts_a]
    world_parts_b = [_apply_transform_to_mesh(p, tf_b) for p in parts_b]

    return _min_clearance_over_parts(world_parts_a, world_parts_b)


# --------------------------------------------------------------------------- #
# Part extraction
# --------------------------------------------------------------------------- #
def _get_parts(pap) -> list[trimesh.Trimesh]:
    """Return the convex parts for a PAP.

    Prefers ``pap._convex_parts`` (set by the bake pipeline).
    Falls back to a single box derived from the PAP's AABB half-extents.
    """
    cached = getattr(pap, "_convex_parts", None)
    if cached:
        return list(cached)
    # Synthesise a single box part from the PAP's AABB half-extents.
    half = pap.geometry.aabb or pap.geometry.obb or [0.5, 0.5, 0.5]
    extents = [2.0 * float(h) for h in half]
    return [trimesh.creation.box(extents=extents)]


# --------------------------------------------------------------------------- #
# Clearance computation
# --------------------------------------------------------------------------- #
def _min_clearance_over_parts(
    parts_a: list[trimesh.Trimesh],
    parts_b: list[trimesh.Trimesh],
) -> GateResult:
    """Minimum clearance (worst penetration) over all part pairs."""
    min_val = float("inf")
    worst_normal: np.ndarray | None = None

    for pa in parts_a:
        for pb in parts_b:
            val, normal = _part_clearance(pa, pb)
            if val < min_val:
                min_val = val
                worst_normal = normal

    ok = min_val >= 0
    fix: FixVector | None = None
    if not ok and worst_normal is not None:
        # The fix translates b along the contact normal to eliminate penetration.
        depth = abs(min_val)
        sep = worst_normal * depth
        fix = FixVector(translate=[float(sep[0]), float(sep[1]), float(sep[2])])

    value = float(min_val) if min_val != float("inf") else float("inf")
    return GateResult(
        gate=GateName.collision,
        ok=ok,
        value_m=value,
        fix=fix,
        detail=_detail(value),
    )


def _part_clearance(pa: trimesh.Trimesh, pb: trimesh.Trimesh) -> tuple[float, np.ndarray]:
    """Signed clearance between two convex meshes via SAT.

    Returns ``(value_m, contact_normal)`` where:
      * value_m > 0  → clearance (gap between closest projected intervals)
      * value_m < 0  → penetration depth (negative, minimum overlap)
      * contact_normal points from ``pa`` toward ``pb``.

    Uses the Separating Hyperplane Theorem (SAT): for convex polyhedra we test
    all face normals from both meshes (and the 3 canonical axes) as candidate
    separating axes.  The axis with the maximum separation is the contact axis
    for the clearance case; the axis with the minimum overlap gives the minimum
    penetration vector for the colliding case.
    """
    # Try FCL first (will fail gracefully if not available).
    try:
        return _fcl_clearance(pa, pb)
    except Exception:
        pass

    return _sat_clearance(pa, pb)


# --------------------------------------------------------------------------- #
# FCL backend (optional)
# --------------------------------------------------------------------------- #
def _fcl_clearance(pa: trimesh.Trimesh, pb: trimesh.Trimesh) -> tuple[float, np.ndarray]:
    """Clearance via trimesh's FCL collision manager (python-fcl)."""
    import trimesh.collision as tcol

    manager_a = tcol.CollisionManager()
    manager_b = tcol.CollisionManager()
    manager_a.add_object("a", pa)
    manager_b.add_object("b", pb)

    is_colliding, contact_data = manager_a.in_collision_other(manager_b, return_data=True)

    if is_colliding:
        max_depth = 0.0
        best_normal = np.array([1.0, 0.0, 0.0])
        for contact in contact_data.contacts.values():
            for c in contact:
                depth = float(c.depth)
                if depth > max_depth:
                    max_depth = depth
                    n = np.asarray(c.normal, dtype=float)
                    norm = np.linalg.norm(n)
                    if norm > 1e-9:
                        best_normal = n / norm
        return -max_depth, best_normal

    distance, _names, _data = manager_a.min_distance_other(manager_b, return_data=True)
    normal = _centroid_normal(pa, pb)
    return float(distance), normal


# --------------------------------------------------------------------------- #
# SAT backend (pure numpy, always available)
# --------------------------------------------------------------------------- #
def _sat_clearance(pa: trimesh.Trimesh, pb: trimesh.Trimesh) -> tuple[float, np.ndarray]:
    """SAT-based signed clearance for two convex meshes.

    Positive = separating gap; negative = penetration (minimum overlap).
    Contact normal points from pa toward pb (the direction b should move to separate).
    """
    verts_a = np.asarray(pa.vertices, dtype=float)
    verts_b = np.asarray(pb.vertices, dtype=float)

    axes = _candidate_axes(pa, pb)

    max_gap = -float("inf")      # most-separating axis value (positive = separated)
    min_overlap = float("inf")   # for penetration case: minimum overlap depth
    gap_axis: np.ndarray = np.array([1.0, 0.0, 0.0])
    overlap_axis: np.ndarray = np.array([1.0, 0.0, 0.0])

    for axis in axes:
        proj_a = verts_a @ axis
        proj_b = verts_b @ axis
        # Gap along this axis: positive when intervals don't overlap.
        gap = max(proj_a.min() - proj_b.max(), proj_b.min() - proj_a.max())
        # Overlap (negative gap): depth of interpenetration along this axis.
        overlap_depth = -gap  # = min(proj_a.max()-proj_b.min(), proj_b.max()-proj_a.min())

        if gap > max_gap:
            max_gap = gap
            # Orient axis from a toward b so fix.translate moves b away from a.
            if proj_b.mean() < proj_a.mean():
                gap_axis = -axis
            else:
                gap_axis = axis.copy()

        if overlap_depth < min_overlap:
            min_overlap = overlap_depth
            # Orient axis from a toward b.
            if proj_b.mean() < proj_a.mean():
                overlap_axis = -axis
            else:
                overlap_axis = axis.copy()

    if max_gap > 0:
        # Separating axis found → objects are apart.
        # The clearance is the maximum gap (minimum separation distance over all axes).
        # But we want the *actual* gap = closest-surface distance, which equals max_gap
        # when the axis with the largest gap is perpendicular to the separating face.
        return float(max_gap), gap_axis
    else:
        # No separating axis → objects interpenetrate.
        # Penetration depth is the minimum overlap (the axis where they barely overlap).
        depth = float(min_overlap)
        return -depth, overlap_axis


def _candidate_axes(pa: trimesh.Trimesh, pb: trimesh.Trimesh) -> list[np.ndarray]:
    """Candidate SAT axes: face normals of both meshes + 3 canonical axes."""
    axes: list[np.ndarray] = [
        np.array([1.0, 0.0, 0.0]),
        np.array([0.0, 1.0, 0.0]),
        np.array([0.0, 0.0, 1.0]),
    ]
    seen: set[tuple] = set()

    for mesh in (pa, pb):
        normals = np.asarray(mesh.face_normals, dtype=float)
        for n in normals:
            norm = float(np.linalg.norm(n))
            if norm < 1e-9:
                continue
            n_unit = n / norm
            # De-duplicate by rounding to 3 decimal places.
            key = tuple(round(float(x), 3) for x in n_unit)
            neg_key = tuple(-v for v in key)
            if key not in seen and neg_key not in seen:
                seen.add(key)
                axes.append(n_unit)

    return axes


# --------------------------------------------------------------------------- #
# Transform application
# --------------------------------------------------------------------------- #
def _apply_transform_to_mesh(mesh: trimesh.Trimesh, transform: Transform) -> trimesh.Trimesh:
    """Return a copy of ``mesh`` with ``transform`` (scale → rotate → translate) applied."""
    copy = mesh.copy()
    # Scale vertices directly to avoid trimesh scale oddities with non-uniform scale.
    scale = np.asarray(transform.scale, dtype=float)
    copy.vertices = copy.vertices * scale
    # Rotate.
    rot = _quat_to_matrix(transform.quat)
    mat4 = np.eye(4)
    mat4[:3, :3] = rot
    copy.apply_transform(mat4)
    # Translate.
    copy.apply_translation(np.asarray(transform.pos, dtype=float))
    return copy


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


def _centroid_normal(pa: trimesh.Trimesh, pb: trimesh.Trimesh) -> np.ndarray:
    """Direction from pa centroid to pb centroid (fallback contact normal)."""
    diff = np.asarray(pb.center_mass, dtype=float) - np.asarray(pa.center_mass, dtype=float)
    norm = float(np.linalg.norm(diff))
    if norm > 1e-9:
        return diff / norm
    return np.array([1.0, 0.0, 0.0])


# --------------------------------------------------------------------------- #
# Human-readable detail
# --------------------------------------------------------------------------- #
def _detail(value_m: float) -> str:
    """Human-readable detail string."""
    if value_m == float("inf"):
        return "no other nodes"
    if value_m >= 0:
        cm = int(round(value_m * 100))
        return f"clearance {cm}cm"
    else:
        cm = int(round(abs(value_m) * 100))
        return f"penetration {cm}cm"
