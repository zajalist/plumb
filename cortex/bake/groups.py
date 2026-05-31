"""
cortex/bake/groups.py — material-group masks (the real masks for authored models).

A textured model (gltf/glb/obj) ships as several material groups — a tree is
*trunk / branch / leaves*; a chair is *frame / cushion*. Those material groups are
the meaningful **masks**: each is a semantic region with its own material, not an
arbitrary convex hull. This module segments a mesh by material and bakes
composition-aware physics over the groups (mass = Σ ρ·V with a density per material),
which is also what lets us skip CoACD on a 2 M-face tree where it would just time out.

Falls back to ``None`` for single-material meshes so the caller keeps the CoACD path.
Geometry comes from the model itself client-side (the viewport renders the real
textured mesh), so the masks carry metadata only — no per-part vertices.
"""

from __future__ import annotations

import numpy as np
import trimesh

from contracts import Geometry, Physical
from cortex.bake.materials import MASK_PALETTE

__all__ = ["bake_material_groups", "material_density"]

# Density (kg/m³) by material-name keyword — honest, name-driven priors.
_DENSITY = [
    (("leaf", "leaves", "foliage", "frond", "needle", "bush"), "foliage", 250.0),
    (("trunk", "branch", "bark", "wood", "log", "timber", "plank", "oak", "pine"), "wood", 700.0),
    (("metal", "steel", "iron", "bronze", "brass", "alumin", "copper", "chrome"), "metal", 7800.0),
    (("stone", "rock", "granite", "marble", "concrete", "brick", "ceramic"), "stone", 2500.0),
    (("glass", "crystal", "window"), "glass", 2500.0),
    (("plastic", "resin", "rubber", "vinyl"), "plastic", 1100.0),
    (("cloth", "fabric", "leather", "canvas", "cushion", "carpet"), "fabric", 400.0),
    (("water", "liquid"), "water", 1000.0),
]


def material_density(name: str | None) -> tuple[str, float]:
    """Map a material name to a (bucket, density) prior; ``("default", 1000)`` if unknown."""
    n = (name or "").lower()
    for keys, mat, rho in _DENSITY:
        if any(k in n for k in keys):
            return mat, rho
    return "default", 1000.0


def _load_groups(mesh_path: str) -> list[tuple[str, trimesh.Trimesh]]:
    """``[(material_name, geometry), …]`` for a multi-material scene, else ``[]``."""
    loaded = trimesh.load(mesh_path, process=False)
    if not isinstance(loaded, trimesh.Scene):
        return []
    groups: list[tuple[str, trimesh.Trimesh]] = []
    for gname, geo in loaded.geometry.items():
        if not isinstance(geo, trimesh.Trimesh) or len(geo.faces) == 0:
            continue
        mat = getattr(getattr(geo, "visual", None), "material", None)
        name = getattr(mat, "name", None) or gname
        groups.append((str(name), geo))
    return groups if len(groups) >= 2 else []


def _group_volume(geo: trimesh.Trimesh) -> float:
    """Watertight volume, else a convex-hull estimate (open surfaces like leaf cards)."""
    try:
        if geo.is_watertight and abs(geo.volume) > 1e-9:
            return float(abs(geo.volume))
    except Exception:
        pass
    try:
        return float(abs(geo.convex_hull.volume)) * 0.25
    except Exception:
        ext = geo.bounding_box.extents
        return float(ext[0] * ext[1] * ext[2]) * 0.1


def bake_material_groups(mesh_path: str):
    """Bake material-group masks for a multi-material mesh, or ``None`` to fall back.

    Returns ``(Geometry, Physical, masks)`` where ``masks`` is one dict per material
    group (id = material name, density-bucket material, volume/mass + fractions, mask
    colour). Physics is composition-aware over the groups. No per-part vertices — the
    viewport renders the real model client-side.
    """
    try:
        groups = _load_groups(mesh_path)
    except Exception:
        return None
    if not groups:
        return None

    combined = trimesh.util.concatenate([g for _, g in groups])
    vols = [_group_volume(g) for _, g in groups]
    buckets = [material_density(n) for n, _ in groups]
    masses = [v * rho for v, (_, rho) in zip(vols, buckets)]
    coms = [np.asarray(g.center_mass, dtype=float) for _, g in groups]

    total_mass = float(sum(masses)) or 1e-9
    com = np.zeros(3)
    for m, c in zip(masses, coms):
        com += m * c
    com /= total_mass

    inertia = np.zeros((3, 3))
    for (_, g), (_, rho), m, c in zip(groups, buckets, masses, coms):
        try:
            g.density = rho
            ip = np.asarray(g.moment_inertia, dtype=float)
        except Exception:
            ip = np.zeros((3, 3))
        r = com - c
        inertia += ip + m * (float(np.dot(r, r)) * np.eye(3) - np.outer(r, r))
    inertia = 0.5 * (inertia + inertia.T)

    geometry = Geometry(
        obb=[float(e) / 2.0 for e in combined.bounding_box_oriented.primitive.extents],
        aabb=[float(e) / 2.0 for e in combined.bounding_box.extents],
        volume_m3=float(sum(vols)),
        convex_parts=len(groups),
        watertight=bool(combined.is_watertight),
    )
    physical = Physical(
        mass_kg=total_mass,
        com=[float(x) for x in com],
        inertia=[[float(v) for v in row] for row in inertia],
        hollow=any(not g.is_watertight for _, g in groups),
        conf=0.4,
    )

    total_v = float(sum(vols)) or 1e-9
    masks = []
    for i, ((name, g), v, (mat, _rho), m) in enumerate(zip(groups, vols, buckets, masses)):
        masks.append({
            "id": name,
            "idx": i,
            "material": mat,
            "conf": 0.6,
            "source": "mesh",
            "confirmed": False,
            "volume_m3": v,
            "vol_frac": v / total_v,
            "mass_kg": m,
            "mass_frac": m / total_mass,
            "hollow": bool(not g.is_watertight),
            "centroid": [float(x) for x in g.center_mass],
            "extent": [float(e) / 2.0 for e in g.bounding_box.extents],
            "color": MASK_PALETTE[i % len(MASK_PALETTE)],
        })
    return geometry, physical, masks
