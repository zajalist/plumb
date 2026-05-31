"""
Geometry mask providers — deterministic, local, dependency-light (trimesh/numpy).

These are the "deterministic" half of the ML/physics source: no model, no network, no key,
always available. Each operates on the asset's convex parts (which carry verts/tris +
centroid + extent + material + colour), so they need nothing the bake didn't already park.
"""

from __future__ import annotations

import numpy as np

from ..registry import MaskProvider, register


def _part_mesh(part: dict):
    import trimesh
    v, f = part.get("verts"), part.get("tris")
    if not v or not f:
        return None
    return trimesh.Trimesh(vertices=np.asarray(v, float), faces=np.asarray(f, int), process=False)


def _scalar(vals: dict[str, float]) -> dict:
    if not vals:
        return {"per_part": {"part_00": 0.0}, "range": [0.0, 1.0], "ramp": "plasma"}
    lo, hi = float(min(vals.values())), float(max(vals.values()))
    return {"per_part": {k: float(v) for k, v in vals.items()}, "range": [lo, hi], "ramp": "plasma"}


# --- materials (categorical) --------------------------------------------------- #

def _materials(asset, images=None) -> dict:
    groups: dict[str, dict] = {}
    for p in asset.parts:
        mat = str(p.get("material") or "default")
        g = groups.setdefault(mat, {"label": mat, "color": p.get("color", "#7E8AA0"), "part_ids": []})
        g["part_ids"].append(p["id"])
    if not groups:
        groups["default"] = {"label": "default", "color": "#7E8AA0", "part_ids": []}
    return {"regions": list(groups.values())}


# --- curvature (scalar): mean |dihedral angle| per part ------------------------ #

def _curvature(asset, images=None) -> dict:
    vals = {}
    for p in asset.parts:
        m = _part_mesh(p)
        if m is None or not len(m.face_adjacency_angles):
            vals[p["id"]] = 0.0
        else:
            vals[p["id"]] = float(np.mean(np.abs(m.face_adjacency_angles)))
    return _scalar(vals)


# --- thickness (scalar): thinnest dimension of each part ----------------------- #

def _thickness(asset, images=None) -> dict:
    vals = {}
    for p in asset.parts:
        ext = p.get("extent") or [0.1, 0.1, 0.1]
        vals[p["id"]] = 2.0 * float(min(ext))
    return _scalar(vals)


# --- contact_patches (markers): parts sitting near the ground plane ------------ #

def _contact_patches(asset, images=None) -> dict:
    cents = [(p["id"], np.asarray(p.get("centroid", [0, 0, 0]), float)) for p in asset.parts]
    if not cents:
        return {"points": []}
    zs = np.array([c[2] for _, c in cents])
    span = float(zs.max() - zs.min()) or 1.0
    thresh = zs.min() + 0.18 * span
    pts = [{"pos": c.tolist(), "label": "contact", "kind": "contact"}
           for pid, c in cents if c[2] <= thresh]
    return {"points": pts}


# --- symmetry_axes (markers): principal axes via PCA of part vertices ---------- #

def _symmetry_axes(asset, images=None) -> dict:
    pts = []
    for p in asset.parts:
        if p.get("verts"):
            pts.extend(p["verts"])
    if len(pts) < 3:
        for p in asset.parts:
            pts.append(p.get("centroid", [0, 0, 0]))
    V = np.asarray(pts, float)
    center = V.mean(axis=0)
    cov = np.cov((V - center).T)
    w, vecs = np.linalg.eigh(cov)
    order = np.argsort(w)[::-1]
    labels = ["major", "minor", "tertiary"]
    axes = [{"origin": center.tolist(), "dir": vecs[:, order[i]].tolist(), "label": labels[i]}
            for i in range(min(3, vecs.shape[1]))]
    return {"axes": axes}


# --- gravity_field (vector): procedural, renderer reuses the force field -------- #

def _gravity_field(asset, images=None) -> dict:
    return {"field": "gravity"}


register(MaskProvider("materials", "Materials", "geometry", "material", "categorical",
                      False, lambda: True, _materials))
register(MaskProvider("curvature", "Curvature", "geometry", "artistic", "scalar",
                      False, lambda: True, _curvature))
register(MaskProvider("thickness", "Thickness", "geometry", "physics", "scalar",
                      False, lambda: True, _thickness))
register(MaskProvider("contact_patches", "Contact patches", "geometry", "physics", "markers",
                      False, lambda: True, _contact_patches))
register(MaskProvider("symmetry_axes", "Symmetry axes", "geometry", "artistic", "markers",
                      False, lambda: True, _symmetry_axes))
register(MaskProvider("gravity_field", "Gravity / force", "geometry", "physics", "vector",
                      False, lambda: True, _gravity_field))
