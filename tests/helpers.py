"""
Shared test fixtures for the Cortex test suite.

Deterministic trimesh primitives only — NO external asset downloads, so tests run
offline and identically everywhere. Each task adds `tests/test_<module>.py` and
reuses these builders; do not duplicate mesh construction per test file.
"""

from __future__ import annotations

import tempfile

import numpy as np
import trimesh


def make_box(extents=(1.0, 1.0, 1.0), center=(0.0, 0.0, 0.0)) -> trimesh.Trimesh:
    """Axis-aligned box of full `extents`, centered at `center`. Watertight."""
    box = trimesh.creation.box(extents=extents)
    box.apply_translation(np.asarray(center, dtype=float))
    return box


def two_part_topheavy() -> tuple[list[trimesh.Trimesh], dict[str, str]]:
    """
    A heavy small 'body' sitting high on a light wide 'base' — the canonical
    top-heavy fixture. Returns ([base, body], {part_index_or_name: material}).

    Density-weighted CoM must sit ABOVE the naive geometric centroid because the
    bronze body is up top. That property is the proof the composition bake is real.
    """
    base = make_box(extents=(0.4, 0.4, 0.2), center=(0.0, 0.0, 0.1))   # wide, low, stone
    body = make_box(extents=(0.1, 0.1, 0.6), center=(0.0, 0.0, 0.5))   # narrow, high, bronze
    parts = [base, body]
    materials = {"base": "stone", "body": "bronze"}  # by name; map index->name as needed
    return parts, materials


def hollow_shell(outer=0.5, wall=0.05) -> trimesh.Trimesh:
    """A box shell (outer cube minus inner cube) — interior-ray test should read hollow."""
    outer_box = trimesh.creation.box(extents=(outer, outer, outer))
    inner = outer - 2 * wall
    inner_box = trimesh.creation.box(extents=(inner, inner, inner))
    try:
        shell = outer_box.difference(inner_box)
        if shell is not None and shell.volume > 0:
            return shell
    except Exception:
        pass
    # Fallback if no boolean engine: return the outer box (callers should skip-if-solid).
    return outer_box


def save_mesh_tmp(mesh: trimesh.Trimesh, suffix: str = ".obj") -> str:
    """Write a mesh to a temp file and return its path (for path-taking bake funcs)."""
    f = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    f.close()
    mesh.export(f.name)
    return f.name
