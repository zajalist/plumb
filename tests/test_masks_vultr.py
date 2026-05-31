"""Tests for the Vultr-hosted mask providers with the network seam mocked.

Mirrors ``test_masks_ai_hf.py``: registration in the catalog, vertical-band projection for the
segmentation models, ``prompt`` passthrough for the text mask, depth scalar shape, and
``available()`` gating (no URL → unavailable; ``compute`` raises ``RuntimeError``).
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cortex.masks as masks
from cortex.masks import registry, store
from cortex.masks.providers import vultr
from cortex.masks.registry import Asset

masks.load_providers()


def _box_part(pid, center, extents, material="stone", color="#888"):
    import trimesh
    b = trimesh.creation.box(extents=extents)
    b.apply_translation(center)
    return {"id": pid, "idx": 0, "material": material, "color": color,
            "centroid": list(map(float, center)), "extent": [e / 2 for e in extents],
            "verts": b.vertices.tolist(), "tris": b.faces.tolist()}


def _asset():
    return Asset("vultr_asset", parts=[
        _box_part("part_00", [0, 0, 0.1], [0.4, 0.4, 0.2]),
        _box_part("part_01", [0, 0, 0.9], [0.1, 0.1, 0.9]),
    ], images=[b"fake-png"])


def _online(monkeypatch):
    """Make the Vultr box look configured + reachable."""
    monkeypatch.setattr(vultr, "_vultr_url", lambda: "http://box:8001")
    monkeypatch.setattr(vultr, "_vultr_token", lambda: "tok")
    monkeypatch.setattr(vultr, "_health_ok", lambda: True)


def test_providers_registered_in_catalog():
    keys = {p["key"] for p in registry.catalog()}
    assert {"sam_parts", "text_mask", "depth", "part_segmentation_hq"} <= keys
    for p in registry.all_providers():
        if p.source == "vultr":
            assert p.needs_images is True


def test_sam_parts_band_projection(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "BAKES_DIR", tmp_path / "bakes")
    _online(monkeypatch)
    seen = {}

    def fake_request(task, image_bytes, params=None):
        seen["task"] = task
        return [{"label": "base", "score": 0.9}, {"label": "top", "score": 0.8}]

    monkeypatch.setattr(vultr, "_vultr_request", fake_request)
    m = registry.compute(_asset(), "sam_parts")
    assert m.archetype == "categorical" and m.source == "vultr"
    assert seen["task"] == "sam"
    labels = {r["label"] for r in m.data["regions"]}
    assert labels <= {"base", "top"} and labels


def test_part_segmentation_hq_routes_to_segment(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "BAKES_DIR", tmp_path / "bakes")
    _online(monkeypatch)
    seen = {}

    def fake_request(task, image_bytes, params=None):
        seen["task"] = task
        return [{"label": "region", "score": 0.5}]

    monkeypatch.setattr(vultr, "_vultr_request", fake_request)
    m = registry.compute(_asset(), "part_segmentation_hq")
    assert seen["task"] == "segment"
    assert m.data["regions"]


def test_text_mask_passes_prompt(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "BAKES_DIR", tmp_path / "bakes")
    _online(monkeypatch)
    seen = {}

    def fake_request(task, image_bytes, params=None):
        seen["task"] = task
        seen["params"] = params
        return [{"label": "handle", "score": 0.7}]

    monkeypatch.setattr(vultr, "_vultr_request", fake_request)
    asset = _asset()
    asset.mask_params = {"prompt": "handle"}
    m = registry.compute(asset, "text_mask")
    assert seen["task"] == "clipseg"
    assert seen["params"] == {"prompt": "handle"}
    assert m.archetype == "categorical"


def test_depth_scalar_shape(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "BAKES_DIR", tmp_path / "bakes")
    _online(monkeypatch)

    def fake_request(task, image_bytes, params=None):
        assert task == "depth"
        return {"grid": [[0.0, 0.5], [0.5, 1.0]], "min": 0.0, "max": 1.0, "h": 2, "w": 2}

    monkeypatch.setattr(vultr, "_vultr_request", fake_request)
    m = registry.compute(_asset(), "depth")
    assert m.archetype == "scalar"
    # Depth grid projected to a per-part scalar so the existing scalar renderer shows it:
    # image rows map to world height (top of image = top of object).
    # part_00 (bottom, znorm 0) → bottom image row [0.5,1.0] mean 0.75
    # part_01 (top,    znorm 1) → top    image row [0.0,0.5] mean 0.25
    assert m.data["per_part"]["part_00"] == 0.75
    assert m.data["per_part"]["part_01"] == 0.25
    assert m.data["range"] == [0.0, 1.0]
    assert m.data["ramp"] == "viridis"


def test_unavailable_without_url(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "BAKES_DIR", tmp_path / "bakes")
    monkeypatch.setattr(vultr, "_vultr_url", lambda: None)
    try:
        registry.compute(_asset(), "sam_parts")
        assert False, "expected unavailable"
    except RuntimeError:
        pass


def test_unavailable_when_health_down(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "BAKES_DIR", tmp_path / "bakes")
    monkeypatch.setattr(vultr, "_vultr_url", lambda: "http://box:8001")
    monkeypatch.setattr(vultr, "_health_ok", lambda: False)
    assert vultr.available() is False
