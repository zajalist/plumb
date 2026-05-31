"""Tests for the geometry mask providers (Phase B)."""

from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cortex.masks as masks
from cortex.masks import registry, store
from cortex.masks.registry import Asset

masks.load_providers()


def _box_part(pid, center, extents, material, color):
    import trimesh
    b = trimesh.creation.box(extents=extents)
    b.apply_translation(center)
    return {"id": pid, "idx": 0, "material": material, "color": color,
            "centroid": list(map(float, center)), "extent": [e / 2 for e in extents],
            "verts": b.vertices.tolist(), "tris": b.faces.tolist()}


def _asset():
    parts = [
        _box_part("part_00", [0, 0, 0.1], [0.4, 0.4, 0.2], "stone", "#7E8AA0"),   # wide base, low
        _box_part("part_01", [0, 0, 0.9], [0.1, 0.1, 0.9], "wood", "#D9A84C"),    # tall thin top
    ]
    return Asset("geo_asset", parts=parts)


def test_all_geometry_providers_registered():
    cat = {c["key"]: c for c in registry.catalog()}
    for key in ("materials", "curvature", "thickness", "contact_patches", "symmetry_axes", "gravity_field"):
        assert key in cat, f"{key} not registered"
        assert cat[key]["available"] is True


def test_materials_categorical(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "BAKES_DIR", tmp_path / "bakes")
    m = registry.compute(_asset(), "materials")
    assert m.archetype == "categorical"
    labels = {r["label"] for r in m.data["regions"]}
    assert labels == {"stone", "wood"}


def test_scalar_providers_finite_and_deterministic(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "BAKES_DIR", tmp_path / "bakes")
    for key in ("curvature", "thickness"):
        a = registry.compute(_asset(), key)
        b = registry.compute(_asset(), key)
        assert a.archetype == "scalar"
        assert set(a.data["per_part"]) == {"part_00", "part_01"}
        assert all(np.isfinite(v) for v in a.data["per_part"].values())
        assert a.data["per_part"] == b.data["per_part"]  # deterministic
        lo, hi = a.data["range"]
        assert lo <= hi
    # thin top part is thinner than the wide base
    th = registry.compute(_asset(), "thickness")
    assert th.data["per_part"]["part_01"] < th.data["per_part"]["part_00"]


def test_contact_and_symmetry_markers(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "BAKES_DIR", tmp_path / "bakes")
    cp = registry.compute(_asset(), "contact_patches")
    assert cp.archetype == "markers"
    # the low base part is a contact; the high part is not
    assert any(p["label"] == "contact" for p in cp.data["points"])
    assert len(cp.data["points"]) == 1

    sa = registry.compute(_asset(), "symmetry_axes")
    assert len(sa.data["axes"]) == 3


def test_gravity_vector(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "BAKES_DIR", tmp_path / "bakes")
    g = registry.compute(_asset(), "gravity_field")
    assert g.archetype == "vector" and g.data["field"] == "gravity" and g.role == "overlay"
