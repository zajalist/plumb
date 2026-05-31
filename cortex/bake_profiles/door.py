"""
cortex/bake_profiles/door.py — the Articulated (door) profile (Task 11).

The Door profile handles articulated assets with a joint axis and angular range.
Its key contribution is ``swept_volume(pap, transform) -> trimesh.Trimesh``:
the union of all door-hull poses rotated from 0° to ``joint.range_deg`` about
the hinge axis.  This wedge mesh is then stored as a static obstacle node so
the ``door_clear`` constraint (T7) reduces to a plain collision check.

Joint metadata is read from ``pap._joint`` (a dict with keys ``axis``,
``range_deg``, and ``hinge_point`` in asset-local space).  The door panel
geometry is read from ``pap._convex_parts`` (set by the bake pipeline);
falling back to a box derived from the PAP geometry if absent.

Canonical space: Z-up, right-handed, metres.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import trimesh

from contracts import PAP, Geometry, Physical, Semantics, Provenance, Transform


# Number of rotation steps used to sample the swept arc.  More steps = smoother
# wedge but slower build.  32 is plenty for a visual + collision check.
_SWEEP_STEPS = 32


def detect(pap: PAP) -> bool:
    """True when ``pap.profile == 'articulated'`` or semantics class is ``'door'``."""
    if pap.profile == "articulated":
        return True
    if pap.semantics and pap.semantics.cls == "door":
        return True
    return False


def passes(pap: PAP) -> PAP:
    """Return the door PAP enriched with articulation defaults.

    Currently a pass-through: the door profile's metadata (joint, sweep) is
    accessed on-demand via ``pap._joint`` and ``pap._convex_parts``.  Future
    enrichment (e.g. computing the swept-volume at bake time and storing it in
    the PAP) can be added here without changing the protocol.
    """
    return pap


# Profile constants (consumed by __init__.py).
DEFAULT_STATES: list[str] = ["closed", "open", "ajar"]
DEFAULT_REGIONS: list[dict] = []
DEFAULT_CONSTRAINTS: list[dict] = []


def swept_volume(pap: PAP, transform: Transform) -> trimesh.Trimesh:
    """Build a mesh that is the union of all door poses from 0 to range_deg.

    The result is the swept-volume wedge of the door rotating around its hinge
    axis.  This mesh can then be added to the world as a static obstacle so that
    a plain collision check (``door_clear``) detects objects in the door arc.

    Parameters
    ----------
    pap:
        The door PAP.  Must carry ``_joint`` and optionally ``_convex_parts``.
    transform:
        World transform of the door node (applied to the local sweep mesh).

    Returns
    -------
    trimesh.Trimesh:
        The swept wedge mesh in world space.
    """
    joint = _get_joint(pap)
    panel = _get_panel(pap)

    hinge_pt = np.asarray(joint["hinge_point"], dtype=float)
    axis = np.asarray(joint["axis"], dtype=float)
    axis_norm = float(np.linalg.norm(axis))
    if axis_norm < 1e-9:
        axis = np.array([0.0, 0.0, 1.0])
    else:
        axis = axis / axis_norm

    range_deg = float(joint["range_deg"])
    range_rad = math.radians(range_deg)

    # Sample the arc from 0 to range_rad.
    angles = np.linspace(0.0, range_rad, _SWEEP_STEPS)

    swept_parts: list[trimesh.Trimesh] = []
    for angle in angles:
        rotated = _rotate_mesh_about_axis(panel, hinge_pt, axis, angle)
        swept_parts.append(rotated)

    # Combine all sampled poses into a single mesh (convex hull of union).
    # Using convex hull keeps it as one solid mesh; the door wedge is well-
    # approximated by the hull of all sampled panel positions.
    combined_verts = np.vstack([p.vertices for p in swept_parts])
    hull = trimesh.convex.convex_hull(combined_verts)

    # Apply the world transform to bring the sweep into world space.
    hull = _apply_transform_to_mesh(hull, transform)
    return hull


def make_sweep_pap(sweep_mesh: trimesh.Trimesh, sweep_id: str) -> PAP:
    """Wrap a sweep mesh as a PAP node that the collision gate can query.

    The PAP uses the convex hull of the sweep as its single part; the geometry
    fields are derived from the mesh's bounding box.

    Parameters
    ----------
    sweep_mesh:
        The swept-volume wedge mesh (output of :func:`swept_volume`).
    sweep_id:
        A unique asset_id for the sweep PAP node.

    Returns
    -------
    PAP:
        A static obstacle PAP backed by the sweep mesh.
    """
    hull = sweep_mesh.convex_hull
    bounds = hull.bounds  # [[min_x, min_y, min_z], [max_x, max_y, max_z]]
    extents = bounds[1] - bounds[0]
    half = extents / 2.0

    pap = PAP(
        asset_id=sweep_id,
        profile="sweep_obstacle",
        geometry=Geometry(
            aabb=[float(half[0]), float(half[1]), float(half[2])],
            obb=[float(half[0]), float(half[1]), float(half[2])],
            volume_m3=float(hull.volume),
            convex_parts=1,
            watertight=True,
        ),
        physical=Physical(
            mass_kg=0.0,  # Static obstacle — mass is irrelevant.
            com=[float(c) for c in hull.center_mass],
        ),
        semantics=Semantics(cls="sweep_obstacle", affordances=[]),
        provenance=Provenance(auto=True),
    )
    # Attach the mesh so the collision gate can use it directly.
    pap.__dict__["_convex_parts"] = [hull]
    return pap


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_joint(pap: PAP) -> dict[str, Any]:
    """Read joint metadata from ``pap._joint``; return sensible defaults if absent."""
    joint = getattr(pap, "_joint", None) or pap.__dict__.get("_joint", None)
    if joint is None:
        # Fallback: a Z-axis hinge at origin with 90° range.
        return {
            "axis": [0.0, 0.0, 1.0],
            "range_deg": 90.0,
            "hinge_point": [0.0, 0.0, 0.0],
        }
    return joint


def _get_panel(pap: PAP) -> trimesh.Trimesh:
    """Return the door panel mesh from ``pap._convex_parts`` or derive from geometry."""
    parts = getattr(pap, "_convex_parts", None) or pap.__dict__.get("_convex_parts", None)
    if parts:
        # Use the first (or merged) convex part as the door panel.
        if len(parts) == 1:
            return parts[0].copy()
        # Multiple parts: merge into one panel.
        merged_verts = np.vstack([p.vertices for p in parts])
        return trimesh.convex.convex_hull(merged_verts)

    # Fallback: build a box from the PAP AABB.
    half = pap.geometry.aabb or pap.geometry.obb or [0.5, 0.5, 0.5]
    extents = [2.0 * float(h) for h in half]
    box = trimesh.creation.box(extents=extents)
    # Shift so the hinge is at x=0 (door extends along +x).
    box.apply_translation([float(half[0]), 0.0, float(half[2])])
    return box


def _rotate_mesh_about_axis(
    mesh: trimesh.Trimesh,
    hinge_pt: np.ndarray,
    axis: np.ndarray,
    angle_rad: float,
) -> trimesh.Trimesh:
    """Return a copy of ``mesh`` rotated by ``angle_rad`` around ``axis`` at ``hinge_pt``."""
    copy = mesh.copy()
    # Build rotation matrix via Rodrigues.
    rot = _axis_angle_to_matrix(axis, angle_rad)
    # Translate to origin, rotate, translate back.
    copy.vertices = copy.vertices - hinge_pt
    copy.vertices = (rot @ copy.vertices.T).T
    copy.vertices = copy.vertices + hinge_pt
    return copy


def _axis_angle_to_matrix(axis: np.ndarray, angle: float) -> np.ndarray:
    """Rodrigues rotation matrix: rotate by ``angle`` radians around unit ``axis``."""
    c = math.cos(angle)
    s = math.sin(angle)
    t = 1.0 - c
    x, y, z = float(axis[0]), float(axis[1]), float(axis[2])
    return np.array(
        [
            [t * x * x + c,     t * x * y - s * z, t * x * z + s * y],
            [t * x * y + s * z, t * y * y + c,     t * y * z - s * x],
            [t * x * z - s * y, t * y * z + s * x, t * z * z + c     ],
        ],
        dtype=float,
    )


def _apply_transform_to_mesh(mesh: trimesh.Trimesh, transform: Transform) -> trimesh.Trimesh:
    """Apply ``transform`` (scale → rotate → translate) to ``mesh``."""
    copy = mesh.copy()
    scale = np.asarray(transform.scale, dtype=float)
    copy.vertices = copy.vertices * scale
    rot = _quat_to_matrix(transform.quat)
    mat4 = np.eye(4)
    mat4[:3, :3] = rot
    copy.apply_transform(mat4)
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
