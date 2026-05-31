"""
cortex/bake/cap.py — manual plane cap: close selected boundary holes with a flat lid.

The studio's manual cap tool lets a user place a finite plane over an opening in the
viewport. This module closes exactly the boundary loops that plane covers — a loop whose
centroid sits inside the plane rectangle and within its slab — by fan-triangulating the
loop to its own centroid. No geometry is removed (it's a lid laid over the hole), so the
mesh becomes watertight and the bake reports a real enclosed volume instead of the wall
estimate.

The plane is given in the mesh's own (native, scene-frame) coordinates — the same frame
the studio derives from the loaded model's local matrix, so a plane the user lined up by
eye in the viewport lands on the same opening here.
"""

from __future__ import annotations

import numpy as np
import trimesh

__all__ = ["cap_with_plane", "cap_file", "boundary_loops"]


def boundary_loops(mesh: trimesh.Trimesh) -> list[list[int]]:
    """Ordered vertex-index loops around every open boundary of ``mesh``.

    Boundary edges are those used by exactly one face. On a manifold-with-boundary each
    boundary vertex has exactly two boundary neighbours, so each loop walks unambiguously
    from any of its edges.
    """
    edges = mesh.edges_sorted
    uniq, counts = np.unique(edges, axis=0, return_counts=True)
    bnd = uniq[counts == 1]
    if len(bnd) == 0:
        return []

    adj: dict[int, list[int]] = {}
    for a, b in bnd:
        adj.setdefault(int(a), []).append(int(b))
        adj.setdefault(int(b), []).append(int(a))

    def key(a: int, b: int) -> tuple[int, int]:
        return (a, b) if a < b else (b, a)

    used: set[tuple[int, int]] = set()
    loops: list[list[int]] = []
    for a0, b0 in bnd:
        a0, b0 = int(a0), int(b0)
        if key(a0, b0) in used:
            continue
        used.add(key(a0, b0))
        loop = [a0, b0]
        prev, cur = a0, b0
        while cur != a0:
            nxt = None
            for n in adj.get(cur, ()):
                if n != prev and key(cur, n) not in used:
                    nxt = n
                    break
            if nxt is None:
                break
            used.add(key(cur, nxt))
            loop.append(nxt)
            prev, cur = cur, nxt
        if loop and loop[-1] == a0:
            loop.pop()
        if len(loop) >= 3:
            loops.append(loop)
    return loops


def _plane_basis(normal):
    n = np.asarray(normal, dtype=float)
    nn = float(np.linalg.norm(n))
    if nn < 1e-12:
        return None, None, None
    n = n / nn
    seed = np.array([1.0, 0.0, 0.0]) if abs(n[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    u = np.cross(n, seed)
    u /= float(np.linalg.norm(u)) or 1.0
    v = np.cross(n, u)
    return n, u, v


def _section_caps(geo, o, n, half):
    """Triangulated floor(s) at the mesh's cross-section through the plane, restricted to
    the lid rectangle. Returns ``(vertices, faces)`` to append, or ``(None, None)``.

    This is the robust primitive: it works on messy game shells (no clean boundary loop
    needed) and never removes geometry — it lays a flat lid across the opening the plane
    cuts. The cap vertices come from the cut edges, so they weld to the mesh.
    """
    try:
        from trimesh.creation import triangulate_polygon

        section = geo.section(plane_origin=o, plane_normal=n)
        if section is None:
            return None, None
        planar, to_3d = section.to_2D()
        polys = list(planar.polygons_full)
        if not polys:
            return None, None
        inv = np.linalg.inv(to_3d)
        o2 = trimesh.transform_points(o.reshape(1, 3), inv)[0][:2]
        add_v: list[np.ndarray] = []
        add_f: list[np.ndarray] = []
        base = 0
        for poly in polys:
            # the lid must actually cover this cross-section piece — i.e. the opening's
            # 2D bounding box fits inside the lid rectangle centred on the plane origin.
            minx, miny, maxx, maxy = poly.bounds
            if (minx < o2[0] - half or maxx > o2[0] + half
                    or miny < o2[1] - half or maxy > o2[1] + half):
                continue
            try:
                v2, f = triangulate_polygon(poly)
            except Exception:
                continue
            if len(v2) == 0 or len(f) == 0:
                continue
            v3 = trimesh.transform_points(np.column_stack([v2, np.zeros(len(v2))]), to_3d)
            add_v.append(v3)
            add_f.append(np.asarray(f) + base)
            base += len(v3)
        if not add_v:
            return None, None
        return np.vstack(add_v), np.vstack(add_f)
    except Exception:
        return None, None


def _loop_caps(geo, o, n, u, v, half, depth):
    """Fallback: fan-fill the open boundary loops the lid rectangle covers (good for clean
    single openings where a section may not close). Returns ``(vertices, faces)`` or
    ``(None, None)``."""
    try:
        loops = boundary_loops(geo)
    except Exception:
        return None, None
    if not loops:
        return None, None
    verts = geo.vertices
    add_v: list[np.ndarray] = []
    add_f: list[list[int]] = []
    base = 0
    for loop in loops:
        pts = verts[loop]
        c = pts.mean(axis=0)
        if abs(float(np.dot(c - o, n))) > depth:
            continue  # loop's plane is outside the lid slab
        rel = pts - o
        du = rel @ u
        dv = rel @ v
        if du.max() > half or du.min() < -half or dv.max() > half or dv.min() < -half:
            continue  # loop doesn't fit inside the lid rectangle
        center_idx = base
        base += 1
        add_v.append(c)
        m = len(loop)
        for i in range(m):
            # loop indices are into geo.vertices; offset added later relative to that base
            add_f.append([center_idx, -1 - loop[i], -1 - loop[(i + 1) % m]])
    if not add_v:
        return None, None
    return np.asarray(add_v, dtype=float), add_f


def cap_with_plane(geo: trimesh.Trimesh, origin, normal, half: float, depth: float):
    """Close the opening the plane rectangle covers with a flat lid. Returns
    ``(geo, n_capped)``.

    ``origin``/``normal`` define the plane; ``half`` is its in-plane half-extent (a square
    2·half on a side); ``depth`` is the slab half-thickness used by the boundary-loop
    fallback. Primary path is a triangulated cross-section floor (robust on messy meshes,
    removes nothing); if the section yields nothing, fan-fill the boundary loops under the
    lid. The new mesh welds the cap to the surface so a sealed region becomes watertight.
    """
    n, u, v = _plane_basis(normal)
    if n is None:
        return geo, 0
    o = np.asarray(origin, dtype=float)
    half = float(half)
    depth = float(depth)

    add_v, add_f = _section_caps(geo, o, n, half)
    used_section = add_v is not None
    if not used_section:
        lv, lf = _loop_caps(geo, o, n, u, v, half, depth)
        if lv is None:
            return geo, 0
        # loop faces reference existing verts via negative sentinels; resolve them now
        nbase = len(geo.vertices)
        faces = []
        for tri in lf:
            faces.append([(nbase + idx) if idx >= 0 else (-1 - idx) for idx in tri])
        all_v = np.vstack([geo.vertices, lv])
        all_f = np.vstack([np.asarray(geo.faces), np.asarray(faces, dtype=np.int64)])
        capped = len(lv)
    else:
        nbase = len(geo.vertices)
        all_v = np.vstack([geo.vertices, add_v])
        all_f = np.vstack([np.asarray(geo.faces), np.asarray(add_f, dtype=np.int64) + nbase])
        capped = len(add_f)

    out = trimesh.Trimesh(vertices=all_v, faces=all_f, process=False)
    try:
        out.merge_vertices()
        out.update_faces(out.nondegenerate_faces())
        trimesh.repair.fix_normals(out)
    except Exception:
        pass
    return out, int(capped)


def cap_file(mesh_path: str, plane: dict) -> str | None:
    """Cap a single-mesh file with ``plane`` and export to a temp ``.obj``.

    Used for the single-material path (the material-group path caps each group in place).
    Returns the new path, or ``None`` if nothing was capped / on failure.
    """
    import tempfile

    try:
        mesh = trimesh.load(mesh_path, force="mesh", process=False)
        if not isinstance(mesh, trimesh.Trimesh):
            return None
        capped, n = cap_with_plane(
            mesh,
            plane.get("origin", [0.0, 0.0, 0.0]),
            plane.get("normal", [0.0, 0.0, 1.0]),
            plane.get("half", 1.0),
            plane.get("depth", 1.0),
        )
        if not n:
            return None
        out = tempfile.NamedTemporaryFile(suffix=".obj", delete=False)
        out.close()
        capped.export(out.name)
        return out.name
    except Exception:
        return None
