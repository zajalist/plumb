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


def test_validate_then_repair_flips_stability_to_green():
    # bake the asset so the backend knows its PAP
    files = {"mesh": ("fig.obj", _combined_mesh_bytes(), "text/plain")}
    obj = client.post("/bake", files=files).json()["asset_id"]

    # place it well off-centre -> its CoM slides off the support footprint -> unstable
    bad = {"object": obj, "pos": [0.30, 0.0, 0.40]}
    v = client.post("/validate", json=bad)
    assert v.status_code == 200, v.text
    verdict = v.json()
    stability = next(g for g in verdict["gates"] if g["gate"] == "stability")
    assert stability["value_m"] is not None      # a real margin number, not a bare no
    assert stability["ok"] is False              # off-centre placement fails stability

    # the SLSQP repair returns a transform...
    fix = client.post("/repair", json=bad).json()
    assert len(fix["pos"]) == 3

    # ...and validating the repaired placement passes stability
    good = {"object": obj, "pos": fix["pos"], "quat": fix["quat"]}
    verdict2 = client.post("/validate", json=good).json()
    stability2 = next(g for g in verdict2["gates"] if g["gate"] == "stability")
    assert stability2["ok"] is True


def test_validate_unknown_asset_is_404():
    r = client.post("/validate", json={"object": "nope", "pos": [0, 0, 0]})
    assert r.status_code == 404
