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

# (keywords, bucket, density kg/m³, is_shell). ``is_shell`` materials are modelled as
# thin surfaces (leaf cards, cloth) — their mass is area × a few-mm thickness, not the
# convex-hull volume, which would absurdly dominate (a tree is wood, not leaves).
_DENSITY = [
    (("leaf", "leaves", "foliage", "frond", "needle", "bush"), "foliage", 500.0, True),
    (("trunk", "branch", "bark", "wood", "log", "timber", "plank", "oak", "pine"), "wood", 700.0, False),
    (("metal", "steel", "iron", "bronze", "brass", "alumin", "copper", "chrome"), "metal", 7800.0, False),
    (("stone", "rock", "granite", "marble", "concrete", "brick", "ceramic"), "stone", 2500.0, False),
    (("glass", "crystal", "window"), "glass", 2500.0, False),
    (("plastic", "resin", "rubber", "vinyl"), "plastic", 1100.0, False),
    (("cloth", "fabric", "leather", "canvas", "cushion", "carpet", "curtain"), "fabric", 400.0, True),
    (("water", "liquid"), "water", 1000.0, False),
]
_SHELL_THICKNESS_M = 0.003  # 3 mm — leaf-card / cloth thickness for shell mass


def _material_info(name: str | None) -> tuple[str, float, bool]:
    """Map a material name to ``(bucket, density, is_shell)``; ``("default", 1000, False)``."""
    n = (name or "").lower()
    for keys, mat, rho, shell in _DENSITY:
        if any(k in n for k in keys):
            return mat, rho, shell
    return "default", 1000.0, False


def material_density(name: str | None) -> tuple[str, float]:
    """``(bucket, density)`` for a material name (back-compat helper)."""
    mat, rho, _ = _material_info(name)
    return mat, rho


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


def _group_volume(geo: trimesh.Trimesh, is_shell: bool) -> float:
    """Volume (m³) for a group: shells → area × thickness; solids → watertight/hull."""
    if is_shell:
        try:
            return float(geo.area) * _SHELL_THICKNESS_M
        except Exception:
            return 0.0
    try:
        if geo.is_watertight and abs(geo.volume) > 1e-12:
            return float(abs(geo.volume))
    except Exception:
        pass
    try:
        return float(abs(geo.convex_hull.volume)) * 0.5
    except Exception:
        ext = geo.bounding_box.extents
        return float(ext[0] * ext[1] * ext[2]) * 0.2


def _unit_scale(combined: trimesh.Trimesh) -> float:
    """Detect a scale to bring an off-unit model (cm/mm) into plausible metres.

    glTF/FBX asset packs vary (cm is common). If the largest dimension already sits in
    a plausible prop range we leave it; otherwise we try the standard unit factors and
    pick the one that lands it in range. Conservative: returns 1.0 if nothing fits.
    """
    try:
        d = float(max(combined.bounding_box.extents))
    except Exception:
        return 1.0
    if d <= 0 or 0.02 <= d <= 25.0:
        return 1.0
    for s in (0.01, 0.001, 0.0001, 10.0, 100.0):
        if 0.02 <= d * s <= 25.0:
            return s
    return 1.0


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

    # Normalise off-unit models (cm/mm) to metres so mass/CoM read true.
    scale = _unit_scale(trimesh.util.concatenate([g for _, g in groups]))
    if scale != 1.0:
        for _, g in groups:
            g.apply_scale(scale)
    combined = trimesh.util.concatenate([g for _, g in groups])

    infos = [_material_info(n) for n, _ in groups]
    vols = [_group_volume(g, info[2]) for (_, g), info in zip(groups, infos)]
    masses = [v * info[1] for v, info in zip(vols, infos)]
    coms = [np.asarray(g.center_mass, dtype=float) for _, g in groups]

    total_mass = float(sum(masses)) or 1e-9
    com = np.zeros(3)
    for m, c in zip(masses, coms):
        com += m * c
    com /= total_mass

    inertia = np.zeros((3, 3))
    for (_, g), info, m, c in zip(groups, infos, masses, coms):
        try:
            g.density = info[1]
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
    for i, ((name, g), v, (mat, _rho, _shell), m) in enumerate(zip(groups, vols, infos, masses)):
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
