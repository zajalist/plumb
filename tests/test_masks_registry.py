"""Tests for cortex/masks registry + Asset adapter + compute (Phase A)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cortex.masks import registry, store
from cortex.masks.registry import Asset, MaskProvider, compute


def _dummy_provider() -> MaskProvider:
    return MaskProvider(
        key="dummy_scalar", name="Dummy", source="geometry", category="physics",
        archetype="scalar", needs_images=False, available=lambda: True,
        compute=lambda asset, images: {
            "per_part": {p["id"]: float(i) for i, p in enumerate(asset.parts)} or {"part_00": 0.0},
            "range": [0.0, 1.0], "confidence": 0.7,
        },
    )


def test_register_and_catalog():
    registry.register(_dummy_provider())
    assert registry.get_provider("dummy_scalar") is not None
    cat = {c["key"]: c for c in registry.catalog()}
    assert cat["dummy_scalar"]["role"] == "surface"
    assert cat["dummy_scalar"]["available"] is True


def test_compute_stores_mask(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "BAKES_DIR", tmp_path / "bakes")
    registry.register(_dummy_provider())
    asset = Asset("asset_z", parts=[{"id": "part_00", "centroid": [0, 0, 0]},
                                    {"id": "part_01", "centroid": [1, 0, 0]}])
    mask = compute(asset, "dummy_scalar")
    assert mask.archetype == "scalar" and mask.confidence == 0.7
    assert mask.data["per_part"]["part_01"] == 1.0
    # persisted
    assert store.get("asset_z", "dummy_scalar") is not None


def test_unavailable_and_unknown(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "BAKES_DIR", tmp_path / "bakes")
    registry.register(MaskProvider(
        key="off", name="Off", source="hf", category="artistic", archetype="scalar",
        needs_images=False, available=lambda: False, compute=lambda a, i: {"per_part": {"p": 0}, "range": [0, 1]},
    ))
    asset = Asset("asset_z", parts=[{"id": "part_00", "centroid": [0, 0, 0]}])
    try:
        compute(asset, "off")
        assert False, "expected unavailable RuntimeError"
    except RuntimeError:
        pass
    try:
        compute(asset, "nope")
        assert False, "expected unknown KeyError"
    except KeyError:
        pass
