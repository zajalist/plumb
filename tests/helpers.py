"""
Shared test helpers for the PLUMB test suite.

Contains two sets of aids — keep both, they serve different subsystems:

  * Cortex helpers (trimesh mesh builders) — deterministic geometry primitives
    used by cortex bake/gate tests.  No external downloads; offline-safe.

  * Conscience helpers (temp paths, UE5 mock payloads) — headless only, no GPU,
    no Unreal; used by conscience unit + integration tests.
"""

from __future__ import annotations

import tempfile

import numpy as np
import trimesh


# ── Cortex helpers — trimesh mesh builders ────────────────────────────────────

def make_box(extents=(1.0, 1.0, 1.0), center=(0.0, 0.0, 0.0)) -> trimesh.Trimesh:
    """Axis-aligned box of full `extents`, centered at `center`. Watertight."""
    box = trimesh.creation.box(extents=extents)
    box.apply_translation(np.asarray(center, dtype=float))
    return box


def two_part_topheavy() -> tuple[list[trimesh.Trimesh], dict[str, str]]:
    """
    A heavy small 'body' sitting high on a light wide 'base' — the canonical
    top-heavy fixture. Returns ([base, body], {part_name: material}).

    Density-weighted CoM must sit ABOVE the naive geometric centroid because the
    bronze body is up top. That property is the proof the composition bake is real.
    """
    base = make_box(extents=(0.4, 0.4, 0.2), center=(0.0, 0.0, 0.1))
    body = make_box(extents=(0.1, 0.1, 0.6), center=(0.0, 0.0, 0.5))
    parts = [base, body]
    materials = {"base": "stone", "body": "bronze"}
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
    return outer_box


def save_mesh_tmp(mesh: trimesh.Trimesh, suffix: str = ".obj") -> str:
    """Write a mesh to a temp file and return its path (for path-taking bake funcs)."""
    f = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    f.close()
    mesh.export(f.name)
    return f.name


# ── Conscience helpers — temp paths + UE5 Remote Control mock payloads ────────

def tmp_path(suffix: str) -> str:
    """A throwaway temp file path (e.g. ".rrd" recordings, ".wdf" docs)."""
    f = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    f.close()
    return f.name


def mock_ue5_actor(
    actor_id: str = "/Game/Maps/Gallery.Gallery:PersistentLevel.BronzeFigure_3",
    location_cm=(-100.0, 200.0, 300.0),
    rotation_quat=(0.0, 0.0, 0.0, 1.0),
    extent_cm=(15.0, 15.0, 75.0),
) -> dict:
    return {
        "actorId": actor_id,
        "location": {"x": location_cm[0], "y": location_cm[1], "z": location_cm[2]},
        "rotation": {"x": rotation_quat[0], "y": rotation_quat[1],
                     "z": rotation_quat[2], "w": rotation_quat[3]},
        "boundsExtent": {"x": extent_cm[0], "y": extent_cm[1], "z": extent_cm[2]},
        "tags": ["plumb"],
    }


def mock_ue5_scene(n: int = 1) -> dict:
    """A Remote Control 'get tagged actors' style response with `n` actors."""
    return {"actors": [mock_ue5_actor(actor_id=f"Actor_{i}") for i in range(n)]}
