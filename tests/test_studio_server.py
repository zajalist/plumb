"""Tests for the PLUMB Studio FastAPI backend (studio/server.py).

These exercise the REAL cortex through the HTTP surface — `/bake` runs the actual
composition bake on a generated mesh and we assert on real numbers, so this is a
genuine end-to-end check of the studio's backend, not a mock.
"""
from __future__ import annotations

import trimesh
from fastapi.testclient import TestClient

from studio.server import app
from tests.helpers import save_mesh_tmp, two_part_topheavy

client = TestClient(app)


def test_health_reports_cortex_present():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["cortex"] is True  # cortex is importable in this env


def _combined_mesh_bytes() -> bytes:
    """One .obj combining the two-part top-heavy fixture (a single uploadable mesh)."""
    parts, _ = two_part_topheavy()
    scene = trimesh.util.concatenate(parts)
    path = save_mesh_tmp(scene, ".obj")
    with open(path, "rb") as f:
        return f.read()


def test_bake_returns_a_pap_with_real_physics():
    files = {"mesh": ("bronze_figure.obj", _combined_mesh_bytes(), "text/plain")}
    r = client.post("/bake", files=files)
    assert r.status_code == 200, r.text
    pap = r.json()
    assert pap["asset_id"] == "bronze_figure"
    # real composition bake produced real numbers
    assert pap["physical"]["mass_kg"] > 0
    assert pap["physical"]["com"][2] > 0.0          # the form is taller than wide
    assert pap["geometry"]["convex_parts"] >= 1
    assert pap["geometry"]["watertight"] in (True, False)


def test_bake_rejects_a_garbage_mesh_cleanly():
    files = {"mesh": ("broken.obj", b"this is not a mesh", "text/plain")}
    r = client.post("/bake", files=files)
    # a bad mesh is a 4xx with a message, never a 500 crash
    assert r.status_code == 422
    assert "bake failed" in r.json()["detail"]
