"""Tests for the studio mask HTTP endpoints (Phase E)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

from cortex.masks import store
from fixtures import BRONZE_FIGURE
from studio.server import _ASSETS, app

client = TestClient(app)


def _box_part(pid, center, extents, material):
    import trimesh
    b = trimesh.creation.box(extents=extents)
    b.apply_translation(center)
    return {"id": pid, "idx": 0, "material": material, "color": "#888",
            "centroid": list(map(float, center)), "extent": [e / 2 for e in extents],
            "verts": b.vertices.tolist(), "tris": b.faces.tolist()}


def test_providers_catalog():
    r = client.get("/masks/providers")
    assert r.status_code == 200
    keys = {p["key"] for p in r.json()["providers"]}
    assert {"materials", "curvature", "gravity_field", "part_segmentation", "fragility"} <= keys


def test_health_has_hf():
    h = client.get("/health").json()
    assert "hf" in h and "available" in h["hf"]


def test_compute_get_delete_geometry(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "BAKES_DIR", tmp_path / "bakes")
    aid = "api_asset"
    _ASSETS[aid] = BRONZE_FIGURE
    store.save_parts(aid, [_box_part("part_00", [0, 0, 0.1], [0.4, 0.4, 0.2], "stone"),
                           _box_part("part_01", [0, 0, 0.9], [0.1, 0.1, 0.9], "wood")])

    assert client.get(f"/masks/{aid}").json()["masks"] == []

    r = client.post(f"/masks/{aid}/compute", data={"provider_key": "materials"})
    assert r.status_code == 200, r.text
    assert r.json()["archetype"] == "categorical"

    got = client.get(f"/masks/{aid}").json()["masks"]
    assert len(got) == 1 and got[0]["id"] == "materials"

    assert client.delete(f"/masks/{aid}/materials").json()["ok"] is True
    assert client.get(f"/masks/{aid}").json()["masks"] == []


def test_compute_unknown_asset():
    r = client.post("/masks/nope_asset/compute", data={"provider_key": "materials"})
    assert r.status_code == 404


def test_compute_unavailable_provider_without_key(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "BAKES_DIR", tmp_path / "bakes")
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGINGFACEHUB_API_TOKEN", raising=False)
    from cortex.masks.providers import hf
    monkeypatch.setattr(hf, "_hf_token", lambda: None)
    aid = "api_asset2"
    _ASSETS[aid] = BRONZE_FIGURE
    store.save_parts(aid, [_box_part("part_00", [0, 0, 0], [0.2, 0.2, 0.2], "stone")])
    r = client.post(f"/masks/{aid}/compute", data={"provider_key": "part_segmentation"})
    assert r.status_code == 503
