"""
Tests for cortex/bake/geometry.py — the geometric bake (Task 2).

Deterministic trimesh primitives only (see tests/helpers.py) — no external asset
downloads. The headline properties: a unit cube bakes to volume ≈ 1.0, watertight
True, OBB half-extents ≈ [0.5, 0.5, 0.5], and at least one convex part; a mesh
with a missing face reads watertight False. Every bake carries a ``decomposition``
flag of ``"coacd"`` or ``"fallback"`` so we never silently ship worse parts.
"""

from __future__ import annotations

import math

import trimesh

from cortex.bake.geometry import bake_geometry, bake_geometry_parts
from contracts import Geometry
from tests.helpers import make_box, save_mesh_tmp


def _open_box() -> trimesh.Trimesh:
    """A unit box with one face removed — non-watertight (no boolean engine needed)."""
    box = make_box(extents=(1.0, 1.0, 1.0))
    return trimesh.Trimesh(vertices=box.vertices.copy(), faces=box.faces[1:].copy())


def test_unit_cube_volume_is_one():
    path = save_mesh_tmp(make_box(extents=(1.0, 1.0, 1.0)))
    geom = bake_geometry(path)
    assert isinstance(geom, Geometry)
    assert math.isclose(geom.volume_m3, 1.0, rel_tol=1e-3)


def test_unit_cube_is_watertight():
    path = save_mesh_tmp(make_box(extents=(1.0, 1.0, 1.0)))
    geom = bake_geometry(path)
    assert geom.watertight is True


def test_unit_cube_has_at_least_one_convex_part():
    path = save_mesh_tmp(make_box(extents=(1.0, 1.0, 1.0)))
    geom = bake_geometry(path)
    assert geom.convex_parts >= 1


def test_unit_cube_obb_half_extents():
    path = save_mesh_tmp(make_box(extents=(1.0, 1.0, 1.0)))
    geom = bake_geometry(path)
    assert len(geom.obb) == 3
    for h in geom.obb:
        assert math.isclose(h, 0.5, abs_tol=1e-3)


def test_unit_cube_aabb_half_extents():
    path = save_mesh_tmp(make_box(extents=(1.0, 1.0, 1.0)))
    geom = bake_geometry(path)
    assert len(geom.aabb) == 3
    for h in geom.aabb:
        assert math.isclose(h, 0.5, abs_tol=1e-3)


def test_non_unit_box_obb_half_extents():
    """OBB half-extents track the true box dimensions, not a fixed cube."""
    path = save_mesh_tmp(make_box(extents=(2.0, 0.4, 1.0)))
    geom = bake_geometry(path)
    assert sorted(round(h, 3) for h in geom.obb) == [0.2, 0.5, 1.0]


def test_non_watertight_mesh_reads_not_watertight():
    path = save_mesh_tmp(_open_box())
    geom = bake_geometry(path)
    assert geom.watertight is False


def test_decomposition_flag_is_present_and_valid():
    path = save_mesh_tmp(make_box(extents=(1.0, 1.0, 1.0)))
    _, parts, flag = bake_geometry_parts(path)
    assert flag in ("coacd", "fallback")


def test_parts_are_trimesh_objects():
    path = save_mesh_tmp(make_box(extents=(1.0, 1.0, 1.0)))
    geom, parts, flag = bake_geometry_parts(path)
    assert len(parts) >= 1
    assert all(isinstance(p, trimesh.Trimesh) for p in parts)
    assert geom.convex_parts == len(parts)


def test_parts_volume_roughly_matches_geometry_volume():
    """Convex parts of a convex cube should reconstruct ≈ the source volume."""
    path = save_mesh_tmp(make_box(extents=(1.0, 1.0, 1.0)))
    geom, parts, _ = bake_geometry_parts(path)
    total = sum(abs(p.volume) for p in parts)
    assert math.isclose(total, geom.volume_m3, rel_tol=0.1)
