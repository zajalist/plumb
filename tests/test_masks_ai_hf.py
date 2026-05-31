"""Tests for HF + Gemini mask providers with the network seams mocked (Phase C)."""

from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cortex.masks as masks
from cortex.masks import registry, store
from cortex.masks.providers import ai, hf
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
    return Asset("aihf_asset", parts=[
        _box_part("part_00", [0, 0, 0.1], [0.4, 0.4, 0.2]),
        _box_part("part_01", [0, 0, 0.9], [0.1, 0.1, 0.9]),
    ], images=[b"fake-png"])


def test_hf_part_segmentation_mocked(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "BAKES_DIR", tmp_path / "bakes")
    monkeypatch.setattr(hf, "_hf_token", lambda: "tok")
    monkeypatch.setattr(hf, "_hf_request", lambda model, img: [
        {"label": "base", "score": 0.9}, {"label": "shaft", "score": 0.8}])
    m = registry.compute(_asset(), "part_segmentation")
    assert m.archetype == "categorical" and m.source == "hf"
    labels = {r["label"] for r in m.data["regions"]}
    assert labels <= {"base", "shaft"} and labels


def test_hf_unavailable_without_token(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "BAKES_DIR", tmp_path / "bakes")
    monkeypatch.setattr(hf, "_hf_token", lambda: None)
    try:
        registry.compute(_asset(), "part_segmentation")
        assert False, "expected unavailable"
    except RuntimeError:
        pass


def test_gemini_fragility_and_affordances_mocked(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "BAKES_DIR", tmp_path / "bakes")
    monkeypatch.setattr(ai, "_gemini_status", lambda: {"available": True})
    monkeypatch.setattr(ai, "_semantic_masks", lambda images, hint="": {
        "fragility": [{"band": "top", "score": 0.9}, {"band": "middle", "score": 0.4},
                      {"band": "bottom", "score": 0.1}],
        "affordances": [{"verb": "grasp", "where": "top"}],
        "confidence": 0.8,
    })
    frag = registry.compute(_asset(), "fragility")
    assert frag.archetype == "scalar" and frag.confidence == 0.8
    assert frag.data["per_part"]["part_01"] == 0.9   # top part
    assert frag.data["per_part"]["part_00"] == 0.1   # bottom part

    aff = registry.compute(_asset(), "affordances")
    assert aff.archetype == "markers"
    assert aff.data["points"][0]["label"] == "grasp"
