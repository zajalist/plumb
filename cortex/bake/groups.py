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
_SOLID_WALL_M = 0.02        # 2 cm — effective wall for open tubular solids (twigs, trunks)
_CAP_MAX_FACES = 350_000    # above this a manual cap's cross-section is too slow — skip the group


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


def _is_shell(name: str, geo: trimesh.Trimesh) -> bool:
    """Is this group an inherent **shell** — a thin open surface (foliage, cloth, or a
    single-sided art mesh) whose mass is area-based, not a closeable solid?

    A material shell (leaf-card / cloth) always is. Otherwise a group counts as a shell
    only if it can't be sealed: it's open and even filling its holes leaves it open (e.g.
    a one-sided bark surface). A solid that's watertight — or open but *fillable* into a
    watertight solid (a barrel with one rim) — is NOT a shell; its opening is closeable.
    This is what lets auto-fill know up front whether it can do anything.
    """
    _b, _r, mat_shell = _material_info(name)
    if mat_shell:
        return True
    try:
        if geo.is_watertight:
            return False
        if len(geo.faces) > _CAP_MAX_FACES:
            return True  # too dense to test cheaply — treat as a surface
        g = geo.copy()
        g.merge_vertices()
        g.update_faces(g.nondegenerate_faces())
        trimesh.repair.fill_holes(g)
        return not bool(g.is_watertight)
    except Exception:
        return True


def _load_groups(mesh_path: str) -> list[tuple[str, trimesh.Trimesh]]:
    """``[(material_name, geometry), …]`` for a multi-material scene, else ``[]``.

    Each geometry is returned with its scene-graph node transform **baked into the
    vertices** (scene frame), so groups share one coordinate frame — the same frame the
    studio derives from the loaded model's local matrix (which lets the manual cap plane
    land on the right opening), and the correct frame for composite CoM/inertia.
    """
    loaded = trimesh.load(mesh_path, process=False)
    if not isinstance(loaded, trimesh.Scene):
        return []
    groups: list[tuple[str, trimesh.Trimesh]] = []
    try:
        nodes = list(loaded.graph.nodes_geometry)
    except Exception:
        nodes = []
    if nodes:
        for node in nodes:
            try:
                transform, gname = loaded.graph[node]
            except Exception:
                continue
            geo = loaded.geometry.get(gname)
            if not isinstance(geo, trimesh.Trimesh) or len(geo.faces) == 0:
                continue
            # Only copy + transform when the node actually moves the geometry — baking an
            # identity transform into millions of leaf verts is pure overhead.
            if transform is not None and not np.allclose(transform, np.eye(4)):
                g = geo.copy()
                try:
                    g.apply_transform(transform)
                except Exception:
                    pass
            else:
                g = geo
            mat = getattr(getattr(g, "visual", None), "material", None)
            name = getattr(mat, "name", None) or gname
            groups.append((str(name), g))
    else:  # no graph instancing info — fall back to the raw geometries
        for gname, geo in loaded.geometry.items():
            if not isinstance(geo, trimesh.Trimesh) or len(geo.faces) == 0:
                continue
            mat = getattr(getattr(geo, "visual", None), "material", None)
            name = getattr(mat, "name", None) or gname
            groups.append((str(name), geo))
    return groups if len(groups) >= 2 else []


def _group_volume(geo: trimesh.Trimesh, is_shell: bool) -> float:
    """Volume (m³) for a group.

    A closed watertight solid → its real enclosed volume. But game meshes are open
    surfaces with ``geo.volume == 0`` (leaf cards, tube-shell trunks/branches), where the
    convex hull wildly overestimates (a tree's branches hull is the whole canopy → tons).
    So a non-watertight group is treated as a surface of an effective wall thickness:
    a few mm for true shells (foliage/cloth), ~2 cm for tubular solids (wood) — giving
    plausible mass instead of a canopy-sized blob.
    """
    try:
        if not is_shell and geo.is_watertight and abs(geo.volume) > 1e-9:
            return float(abs(geo.volume))
    except Exception:
        pass
    try:
        thickness = _SHELL_THICKNESS_M if is_shell else _SOLID_WALL_M
        return float(geo.area) * thickness
    except Exception:
        ext = geo.bounding_box.extents
        return float(ext[0] * ext[1] * ext[2]) * 0.1


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


def _group_com(geo: trimesh.Trimesh) -> np.ndarray:
    """Robust centre of mass. ``geo.center_mass`` needs a watertight volume — for the
    open shells in game meshes (leaf cards, single-sided trunks) it returns garbage and
    skews the whole composite CoM. Fall back to the **area-weighted centroid** (the mass
    centre of a uniform surface), then the vertex centroid."""
    try:
        if geo.is_watertight and abs(geo.volume) > 1e-9:
            return np.asarray(geo.center_mass, dtype=float)
    except Exception:
        pass
    try:
        tc = np.asarray(geo.triangles_center, dtype=float)
        a = np.asarray(geo.area_faces, dtype=float)
        if a.sum() > 1e-12:
            return (tc * a[:, None]).sum(axis=0) / a.sum()
    except Exception:
        pass
    return np.asarray(geo.centroid, dtype=float)


def _group_inertia(geo: trimesh.Trimesh, mass: float) -> np.ndarray:
    """Own inertia tensor about the group's CoM. Watertight → real tensor at our mass;
    otherwise a uniform-box approximation from the bbox (never garbage/NaN)."""
    try:
        if geo.is_watertight and abs(geo.volume) > 1e-9:
            geo.density = mass / float(abs(geo.volume))
            return np.asarray(geo.moment_inertia, dtype=float)
    except Exception:
        pass
    x, y, z = (float(e) for e in geo.bounding_box.extents)
    return (mass / 12.0) * np.diag([y * y + z * z, x * x + z * z, x * x + y * y])


def _close_group(geo: trimesh.Trimesh) -> None:
    """Best-effort close a mesh in place — weld seams, drop degenerate faces, then
    ``fill_holes`` (which triangulates the open boundary loops, i.e. caps the openings
    with planar fills) and fix winding. If it becomes watertight the bake uses its real
    enclosed volume instead of the wall estimate."""
    for step in (
        lambda: geo.merge_vertices(),
        lambda: geo.update_faces(geo.nondegenerate_faces()),
        lambda: trimesh.repair.fill_holes(geo),
        lambda: trimesh.repair.fix_normals(geo),
    ):
        try:
            step()
        except Exception:
            pass


def bake_material_groups(mesh_path: str, cap: bool = False, cap_plane: dict | None = None):
    """Bake material-group masks for a multi-material mesh, or ``None`` to fall back.

    Returns ``(Geometry, Physical, masks)`` where ``masks`` is one dict per material
    group (id = material name, density-bucket material, volume/mass + fractions, mask
    colour). Physics is composition-aware over the groups. ``cap_plane`` (origin / normal
    / half / depth in the mesh's native frame) closes only the openings a user's manual
    plane covers; ``cap`` (no plane) auto-fills every hole. Either makes the volume real,
    not estimated. No per-part vertices — the viewport renders the real model client-side.
    """
    try:
        groups = _load_groups(mesh_path)
    except Exception:
        return None
    if not groups:
        return None

    if cap_plane:
        from cortex.bake.cap import cap_with_plane

        capped: list[tuple[str, trimesh.Trimesh]] = []
        for name, g in groups:
            # Skip thin shells (foliage / cloth — a flat card has nothing to cap) and very
            # dense groups (sectioning millions of faces is what makes a cap hang). Leaves
            # are both, so this keeps the cap responsive on game trees.
            _bucket, _rho, is_shell = _material_info(name)
            if is_shell or len(g.faces) > _CAP_MAX_FACES:
                capped.append((name, g))
                continue
            try:
                g2, _n = cap_with_plane(
                    g,
                    cap_plane.get("origin", [0.0, 0.0, 0.0]),
                    cap_plane.get("normal", [0.0, 0.0, 1.0]),
                    cap_plane.get("half", 1.0),
                    cap_plane.get("depth", 1.0),
                )
                capped.append((name, g2))
            except Exception:
                capped.append((name, g))
        groups = capped
    elif cap:
        # Auto hole-fill, but only on closeable solids — filling a foliage shell's 30 000
        # leaf-card boundaries is pointless and slow, and a huge group would hang.
        for name, g in groups:
            _b, _r, is_sh = _material_info(name)
            if is_sh or len(g.faces) > _CAP_MAX_FACES:
                continue
            _close_group(g)

    # Normalise off-unit models (cm/mm) to metres so mass/CoM read true.
    scale = _unit_scale(trimesh.util.concatenate([g for _, g in groups]))
    if scale != 1.0:
        for _, g in groups:
            g.apply_scale(scale)
    combined = trimesh.util.concatenate([g for _, g in groups])

    infos = [_material_info(n) for n, _ in groups]
    vols = [_group_volume(g, info[2]) for (_, g), info in zip(groups, infos)]
    masses = [v * info[1] for v, info in zip(vols, infos)]
    coms = [_group_com(g) for _, g in groups]

    total_mass = float(sum(masses)) or 1e-9
    com = np.zeros(3)
    for m, c in zip(masses, coms):
        com += m * c
    com /= total_mass

    inertia = np.zeros((3, 3))
    for (_, g), m, c in zip(groups, masses, coms):
        ip = _group_inertia(g, m)
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

    # classify each region: an inherent shell (area-based) vs a closeable solid — drives
    # the studio's closure UX (whether auto-fill / manual capping can do anything).
    shells = [_is_shell(name, g) for name, g in groups]

    total_v = float(sum(vols)) or 1e-9
    masks = []
    for i, ((name, g), v, (mat, _rho, _shell), m, c) in enumerate(zip(groups, vols, infos, masses, coms)):
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
            "shell": bool(shells[i]),   # area-based region (foliage/cloth/one-sided surface)
            "centroid": [float(x) for x in c],
            "extent": [float(e) / 2.0 for e in g.bounding_box.extents],
            "color": MASK_PALETTE[i % len(MASK_PALETTE)],
        })
    return geometry, physical, masks
