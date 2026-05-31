"""
cortex/bake/geometry.py — the geometric bake (Task 2).

Load a mesh with ``trimesh`` and distil its *shape* into the frozen ``Geometry``
contract: axis-aligned and oriented bounding-box half-extents, signed volume,
watertightness, and a convex-part count. The convex parts themselves are returned
alongside (via :func:`bake_geometry_parts`) so the physical bake (Task 3) and the
collision gate (Task 5) can consume them without re-decomposing.

Canonical space everywhere: Z-up, right-handed, metres, kilograms.

Decomposition degrades gracefully (see plans/cortex-plan.md): we try CoACD; if the
``coacd`` import or run fails we fall back to ``trimesh``'s convex decomposition /
hull and tag the result ``decomposition="fallback"`` so we never silently ship
worse parts. The flag rides as the third element of
:func:`bake_geometry_parts`' return so downstream bakes can record provenance —
the ``Geometry`` contract has no field for it and must not be modified.
"""

from __future__ import annotations

import os

import numpy as np
import trimesh

from contracts import Geometry

# CoACD convexity threshold. Lower = more parts / tighter fit; 0.05 is the library
# default and a good speed/quality balance for prop-scale meshes.
_COACD_THRESHOLD = 0.05

# CoACD can run for a very long time on non-watertight meshes (its voxel-remesh
# path) and is a C extension a thread can't interrupt — so we run it in a
# subprocess with a hard timeout and fall back to a convex decomposition / hull if
# it overruns. Tunable for slow machines / dense scenes.
_COACD_TIMEOUT_S = float(os.environ.get("PLUMB_COACD_TIMEOUT", "20"))
# Bounded-cost params: lower preprocess/sampling than the library defaults so a
# messy mesh still finishes; quality stays good on clean (watertight) meshes.
_COACD_PARAMS = dict(
    preprocess_mode="auto", preprocess_resolution=30, resolution=1500,
    mcts_iterations=100, mcts_max_depth=2, mcts_nodes=20, merge=True,
)

DecompositionFlag = str  # "coacd" | "fallback"


def bake_geometry(mesh_path: str) -> Geometry:
    """Bake just the :class:`Geometry` contract object for a mesh on disk."""
    geometry, _parts, _flag = bake_geometry_parts(mesh_path)
    return geometry


def bake_geometry_parts(
    mesh_path: str,
) -> tuple[Geometry, list[trimesh.Trimesh], DecompositionFlag]:
    """Bake geometry **and** keep the raw convex parts + decomposition provenance.

    Returns ``(Geometry, parts, flag)`` where ``parts`` is the list of convex
    ``trimesh.Trimesh`` pieces the rest of the bake consumes and ``flag`` is
    ``"coacd"`` when CoACD produced the decomposition, else ``"fallback"``.
    """
    mesh = _load_mesh(mesh_path)
    _preprocess(mesh)

    parts, flag = _convex_parts(mesh)

    geometry = Geometry(
        obb=_obb_half_extents(mesh),
        aabb=_aabb_half_extents(mesh),
        volume_m3=float(abs(mesh.volume)),
        convex_parts=len(parts),
        watertight=bool(mesh.is_watertight),
    )
    return geometry, parts, flag


# --------------------------------------------------------------------------- #
# Internals
# --------------------------------------------------------------------------- #
def _load_mesh(mesh_path: str) -> trimesh.Trimesh:
    """Load ``mesh_path`` as a single concatenated ``Trimesh`` (handles scenes)."""
    loaded = trimesh.load(mesh_path, force="mesh", process=False)
    if isinstance(loaded, trimesh.Scene):
        loaded = loaded.dump(concatenate=True)
    if not isinstance(loaded, trimesh.Trimesh):
        raise ValueError(f"{mesh_path!r} did not load as a triangle mesh")
    return loaded


def _preprocess(mesh: trimesh.Trimesh) -> None:
    """Light, non-destructive cleanup so CoACD's fast path can trigger.

    Game-engine exports split vertices per corner and leave small gaps, which reads
    as non-watertight and pushes CoACD onto its slow voxel-remesh path. Merging weld
    seams, dropping degenerate/duplicate faces, and filling small holes recovers
    connectivity *without* moving geometry (mass/CoM stay honest — we never voxel-
    remesh, which would distort them). Best-effort: any step that fails is skipped.
    """
    if mesh.is_watertight:
        return
    for step in (
        lambda: mesh.merge_vertices(),
        lambda: mesh.update_faces(mesh.nondegenerate_faces()),
        lambda: mesh.update_faces(mesh.unique_faces()),
        lambda: mesh.remove_unreferenced_vertices(),
        lambda: trimesh.repair.fill_holes(mesh),
        lambda: trimesh.repair.fix_normals(mesh),
    ):
        try:
            step()
        except Exception:
            pass


def _aabb_half_extents(mesh: trimesh.Trimesh) -> list[float]:
    """Half-extents of the axis-aligned bounding box, [hx, hy, hz]."""
    return [float(e) / 2.0 for e in mesh.bounding_box.extents]


def _obb_half_extents(mesh: trimesh.Trimesh) -> list[float]:
    """Half-extents of the minimum-volume oriented bounding box, [hx, hy, hz]."""
    return [float(e) / 2.0 for e in mesh.bounding_box_oriented.primitive.extents]


def _convex_parts(
    mesh: trimesh.Trimesh,
) -> tuple[list[trimesh.Trimesh], DecompositionFlag]:
    """Convex-decompose ``mesh`` via CoACD, falling back gracefully.

    Order of preference: CoACD -> ``trimesh.convex_decomposition`` -> single
    convex hull. Any failure (missing wheel, runtime error, empty result) demotes
    to the next option and tags the result ``"fallback"``.
    """
    coacd_parts = _coacd_parts(mesh)
    if coacd_parts:
        return coacd_parts, "coacd"
    return _fallback_parts(mesh), "fallback"


def _coacd_worker(q, vertices, faces, threshold, params) -> None:
    """Subprocess entry: run CoACD and push ``[(V, F), …]`` (or ``[]`` on error) to ``q``."""
    try:
        import coacd

        coacd.set_log_level("error")
        cmesh = coacd.Mesh(vertices, faces)
        result = coacd.run_coacd(cmesh, threshold=threshold, **params)
        q.put([(np.asarray(v), np.asarray(f)) for v, f in result])
    except Exception:
        q.put([])


def _coacd_parts(mesh: trimesh.Trimesh) -> list[trimesh.Trimesh]:
    """Run CoACD in a subprocess with a hard timeout; ``[]`` on timeout/unavailable.

    The empty return demotes to the graceful fallback in :func:`_convex_parts`, so a
    CoACD hang (it spinning on a non-watertight mesh) can never block a bake. The
    subprocess is the only way to bound a C-extension call — a thread can't kill it.
    """
    try:
        import coacd  # noqa: F401 — probe availability before paying the spawn cost
    except Exception:
        return []

    import multiprocessing as mp
    import queue as _queue

    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    faces = np.asarray(mesh.faces, dtype=np.int32)
    ctx = mp.get_context("spawn")
    q = ctx.Queue()
    proc = ctx.Process(
        target=_coacd_worker, args=(q, vertices, faces, _COACD_THRESHOLD, _COACD_PARAMS),
    )
    proc.start()
    try:
        raw = q.get(timeout=_COACD_TIMEOUT_S)
    except _queue.Empty:
        raw = []  # CoACD overran its budget → fall back to a convex decomposition
    finally:
        if proc.is_alive():
            proc.terminate()
        proc.join(timeout=2)

    parts: list[trimesh.Trimesh] = []
    for part_v, part_f in raw:
        part = trimesh.Trimesh(vertices=np.asarray(part_v), faces=np.asarray(part_f))
        if part.volume and abs(part.volume) > 0:
            parts.append(part)
    return parts


def _fallback_parts(mesh: trimesh.Trimesh) -> list[trimesh.Trimesh]:
    """CoACD-free decomposition: trimesh's own, else a single convex hull."""
    try:
        pieces = mesh.convex_decomposition()
        if isinstance(pieces, trimesh.Trimesh):
            pieces = [pieces]
        parts = [p for p in pieces if isinstance(p, trimesh.Trimesh) and abs(p.volume) > 0]
        if parts:
            return parts
    except Exception:
        pass
    # Last resort: the convex hull is itself one convex part.
    return [mesh.convex_hull]
