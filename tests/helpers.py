"""
Shared test helpers for the PLUMB suite (both halves).

Two families, no overlap in names:
  - Cortex (Person A): deterministic trimesh primitives — box, top-heavy two-part
    fixture, hollow shell, temp-mesh writer. NO external downloads; offline + identical.
  - Conscience (Person B): headless aids — temp paths and an illustrative UE5 Remote
    Control payload for the mock HTTP server (no GPU, no Unreal).
"""

from __future__ import annotations

import tempfile

import numpy as np
import trimesh


# --------------------------------------------------------------------------- #
# Cortex (Person A) — mesh fixtures
# --------------------------------------------------------------------------- #
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


# --------------------------------------------------------------------------- #
# Conscience (Person B) — headless aids
# --------------------------------------------------------------------------- #
def tmp_path(suffix: str) -> str:
    """A throwaway temp file path (e.g. ".rrd" recordings, ".wdf" docs)."""
    f = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    f.close()
    return f.name


# Illustrative UE5 Remote Control response for ONE tagged actor.
# UE5 space: left-handed, Z-up, centimetres. The adapter must convert to canonical
# (right-handed, metres). Shape is representative — the bridge task may refine it,
# but the mock server should serve something like this so parsing is exercised.
def mock_ue5_actor(
    actor_id: str = "/Game/Maps/Gallery.Gallery:PersistentLevel.BronzeFigure_3",
    location_cm=(-100.0, 200.0, 300.0),     # UE5 cm, LH
    rotation_quat=(0.0, 0.0, 0.0, 1.0),     # [x, y, z, w]
    extent_cm=(15.0, 15.0, 75.0),           # half-extents in cm
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


# --------------------------------------------------------------------------- #
# Seam check (used by the conscience "never import cortex" tests)
# --------------------------------------------------------------------------- #
def cortex_modules_after(setup_code: str) -> list[str]:
    """Run ``setup_code`` in a FRESH interpreter and return any ``cortex`` modules it
    pulled into ``sys.modules``. An empty list means the conscience seam held.

    This MUST run in a subprocess: when the cortex test-suite runs in the same pytest
    session it leaves ``cortex`` in the shared ``sys.modules``, so a naive in-process
    check would fail spuriously on a merged tree. A clean interpreter measures only what
    ``setup_code`` actually imports.
    """
    import json
    import os
    import subprocess
    import sys

    code = (
        setup_code
        + "\nimport json as _j, sys as _s\n"
        "print(_j.dumps([m for m in _s.modules if m == 'cortex' or m.startswith('cortex.')]))\n"
    )
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(p for p in sys.path if p))
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)
    assert proc.returncode == 0, f"seam-check subprocess failed:\n{proc.stderr}"
    return json.loads(proc.stdout.strip().splitlines()[-1])
