"""Tests for cortex/masks model + store (Phase A)."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cortex.masks import store
from cortex.masks.model import Mask, derive_legend, role_for


def _mask(archetype: str, **data_over) -> Mask:
    data = {
        "categorical": {"regions": [{"label": "trunk", "color": "#34C0AD", "part_ids": ["part_00"]}]},
        "scalar": {"per_part": {"part_00": 0.2, "part_01": 0.9}, "range": [0.0, 1.0]},
        "vector": {"field": "gravity"},
        "markers": {"points": [{"pos": [0, 0, 1], "label": "grip", "kind": "grasp"}]},
    }[archetype]
    data.update(data_over)
    return Mask(id=f"m_{archetype}", asset_id="asset_a", name=archetype,
                source="geometry", category="physics", archetype=archetype, data=data)


def test_role_derivation():
    assert role_for("categorical") == "surface"
    assert role_for("scalar") == "surface"
    assert role_for("vector") == "overlay"
    assert role_for("markers") == "overlay"


def test_each_archetype_constructs_and_legends():
    cat = _mask("categorical")
    assert cat.role == "surface"
    assert cat.legend["kind"] == "swatches" and cat.legend["items"][0]["label"] == "trunk"

    sca = _mask("scalar")
    assert sca.legend["kind"] == "ramp" and sca.legend["range"] == [0.0, 1.0]

    vec = _mask("vector")
    assert vec.role == "overlay" and vec.legend["kind"] == "none"

    mrk = _mask("markers")
    assert mrk.role == "overlay"


def test_bad_data_raises():
    with pytest.raises(Exception):
        Mask(id="x", asset_id="a", name="bad", source="geometry",
             category="physics", archetype="categorical", data={"regions": []})
    with pytest.raises(Exception):
        Mask(id="x", asset_id="a", name="bad", source="geometry",
             category="physics", archetype="scalar", data={"per_part": {}})


def test_store_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "BAKES_DIR", tmp_path / "bakes")
    assert store.list_masks("asset_a") == []

    m = _mask("scalar")
    store.upsert(m)
    got = store.list_masks("asset_a")
    assert len(got) == 1 and got[0].id == "m_scalar"
    assert store.get("asset_a", "m_scalar").data["per_part"]["part_01"] == 0.9

    # overwrite same id, not duplicate
    store.upsert(_mask("scalar", per_part={"part_00": 0.5}, range=[0.0, 1.0]))
    assert len(store.list_masks("asset_a")) == 1

    assert store.delete("asset_a", "m_scalar") is True
    assert store.list_masks("asset_a") == []
    assert store.delete("asset_a", "nope") is False


def test_store_parts_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "BAKES_DIR", tmp_path / "bakes")
    parts = [{"id": "part_00", "centroid": [0, 0, 0], "verts": [[0, 0, 0]], "tris": [[0, 0, 0]]}]
    store.save_parts("asset_a", parts)
    assert store.load_parts("asset_a")[0]["id"] == "part_00"
    assert store.load_parts("missing") == []
