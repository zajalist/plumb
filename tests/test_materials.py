"""
Tests for cortex/bake/materials.py + bake_asset_detailed — the per-part material
masks the bake emits and the studio renders.

Honesty guarantees under test:
  * one guess per convex part, every guess ``source="default"`` and low-confidence;
  * an auto-bake populates ``semantics.materials`` (the masks) but stays ``auto``,
    locks nothing, and leaves mass at default density (guesses never touch physics);
  * authored materials drive physics, lock the fields, and read back confirmed;
  * the per-part detail reconciles (volume fractions sum to 1).

Deterministic trimesh primitives only (tests/helpers.py).
"""

from __future__ import annotations

import math

import trimesh

from contracts import MaterialGuess
from cortex.bake import bake_asset, bake_asset_detailed
from cortex.bake.materials import guess_materials
from cortex.bake.physical import MATERIAL_DENSITY
from tests.helpers import make_box, save_mesh_tmp, two_part_topheavy


def test_guess_materials_one_low_conf_default_guess_per_part():
    parts, _materials = two_part_topheavy()
    guesses = guess_materials(parts)

    assert len(guesses) == len(parts)
    assert all(isinstance(g, MaterialGuess) for g in guesses)
    assert all(g.source == "default" for g in guesses)      # no VLM — honest label
    assert all(0.0 < g.conf < 1.0 for g in guesses)         # never claims certainty
    assert [g.part for g in guesses] == [f"part_{i:02d}" for i in range(len(parts))]


def test_auto_bake_populates_masks_but_does_not_lock_or_alter_mass():
    path = save_mesh_tmp(make_box(extents=(1.0, 1.0, 1.0)))
    pap = bake_asset("cube_auto", path)

    assert len(pap.semantics.materials) == pap.geometry.convex_parts  # masks present
    assert pap.provenance.auto is True
    assert pap.provenance.locked == []
    # guesses must not move physics: a unit cube stays at default density.
    assert math.isclose(pap.physical.mass_kg, MATERIAL_DENSITY["default"], rel_tol=1e-2)


def test_detailed_parts_reconcile_and_carry_mask_fields():
    mesh = trimesh.util.concatenate(two_part_topheavy()[0])
    path = save_mesh_tmp(mesh)
    pap, parts = bake_asset_detailed("topheavy", path)

    assert len(parts) == pap.geometry.convex_parts
    assert math.isclose(sum(p["vol_frac"] for p in parts), 1.0, rel_tol=1e-6)
    for i, p in enumerate(parts):
        assert p["id"] == f"part_{i:02d}"
        assert p["color"].startswith("#")
        assert p["confirmed"] is False              # auto-bake: nothing confirmed yet
        assert p["material"] in MATERIAL_DENSITY


def test_authored_materials_lock_and_read_back_confirmed():
    path = save_mesh_tmp(make_box(extents=(1.0, 1.0, 1.0)))
    pap, parts = bake_asset_detailed("cube_bronze", path, part_materials={0: "bronze"})

    assert pap.provenance.auto is False
    assert any("material" in f for f in pap.provenance.locked)
    assert parts[0]["material"] == "bronze"
    assert parts[0]["confirmed"] is True
    # bronze drove physics → the part is ~8.8× a default cube.
    assert math.isclose(pap.physical.mass_kg, MATERIAL_DENSITY["bronze"], rel_tol=1e-2)
