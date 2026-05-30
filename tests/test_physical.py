"""
Tests for cortex/bake/physical.py + cortex/bake/__init__.py:bake_asset (Task 3).

The headline bake. Composition-aware mass / CoM / inertia over convex parts:

  * mass   = Σ ρ·V        (each part's density from its material)
  * CoM    = Σ(ρ·V·c)/m   (density-weighted — NOT the uniform geometric centroid)
  * inertia= Σ parallel-axis(I_part, r)   about the composite CoM

The proof the composition math is real is the *top-heavy* property: a heavy small
bronze body stacked high on a light wide stone base must push the density-weighted
CoM **above** the uniform-density (volume-weighted) centroid. Plus: a uniform
single material recovers the geometric centroid; a hollow shell reads hollow; a
unit bronze cube weighs ≈ 8800 kg.

Deterministic trimesh primitives only (tests/helpers.py) — no external assets.
"""

from __future__ import annotations

import math

import numpy as np

from contracts import PAP, Physical
from cortex.bake import bake_asset
from cortex.bake.physical import MATERIAL_DENSITY, bake_physical
from tests.helpers import (
    hollow_shell,
    make_box,
    save_mesh_tmp,
    two_part_topheavy,
)


def _uniform_centroid_z(parts) -> float:
    """Volume-weighted (uniform-density) centroid z over the parts."""
    vols = np.array([abs(p.volume) for p in parts])
    cz = np.array([p.center_mass[2] for p in parts])
    return float((vols * cz).sum() / vols.sum())


# --------------------------------------------------------------------------- #
# bake_physical — composition math
# --------------------------------------------------------------------------- #
def test_top_heavy_com_sits_above_uniform_centroid():
    """THE MOAT: density-weighted CoM rises above the uniform centroid."""
    parts, materials = two_part_topheavy()
    part_materials = {0: materials["base"], 1: materials["body"]}
    phys = bake_physical(parts, part_materials)

    uniform_z = _uniform_centroid_z(parts)
    assert phys.com[2] > uniform_z + 1e-3


def test_uniform_material_com_matches_geometric_centroid():
    """Single uniform material → CoM ≈ volume-weighted geometric centroid."""
    parts, _ = two_part_topheavy()
    part_materials = {0: "stone", 1: "stone"}
    phys = bake_physical(parts, part_materials)

    uniform_z = _uniform_centroid_z(parts)
    assert math.isclose(phys.com[2], uniform_z, abs_tol=1e-6)
    assert math.isclose(phys.com[0], 0.0, abs_tol=1e-6)
    assert math.isclose(phys.com[1], 0.0, abs_tol=1e-6)


def test_inertia_tensor_symmetric_and_positive_diagonal():
    parts, materials = two_part_topheavy()
    part_materials = {0: materials["base"], 1: materials["body"]}
    phys = bake_physical(parts, part_materials)

    I = np.array(phys.inertia)
    assert I.shape == (3, 3)
    assert np.allclose(I, I.T, atol=1e-9)
    assert all(d > 0 for d in np.diag(I))


def test_unit_bronze_cube_mass():
    """ρ_bronze · V(1m³) = 8800 kg."""
    cube = make_box(extents=(1.0, 1.0, 1.0))
    phys = bake_physical([cube], {0: "bronze"})
    assert math.isclose(phys.mass_kg, MATERIAL_DENSITY["bronze"], rel_tol=1e-3)


def test_unknown_material_falls_back_to_default_density():
    cube = make_box(extents=(1.0, 1.0, 1.0))
    phys = bake_physical([cube], {0: "unobtainium"})
    assert math.isclose(phys.mass_kg, MATERIAL_DENSITY["default"], rel_tol=1e-3)


def test_missing_part_material_defaults_to_default():
    """Parts with no entry in part_materials default to 'default'."""
    cube = make_box(extents=(1.0, 1.0, 1.0))
    phys = bake_physical([cube], {})  # no materials given
    assert math.isclose(phys.mass_kg, MATERIAL_DENSITY["default"], rel_tol=1e-3)


def test_hollow_shell_reads_hollow():
    shell = hollow_shell(outer=0.5, wall=0.05)
    phys = bake_physical([shell], {0: "stone"})
    assert phys.hollow is True


def test_solid_box_reads_not_hollow():
    cube = make_box(extents=(0.5, 0.5, 0.5))
    phys = bake_physical([cube], {0: "stone"})
    assert phys.hollow is False


def test_bake_physical_returns_contract_physical():
    cube = make_box(extents=(1.0, 1.0, 1.0))
    phys = bake_physical([cube], {0: "wood"})
    assert isinstance(phys, Physical)
    assert phys.mass_kg > 0
    assert len(phys.com) == 3
    assert len(phys.inertia) == 3


# --------------------------------------------------------------------------- #
# bake_asset — composes geometry (T2) + physical into a full PAP
# --------------------------------------------------------------------------- #
def test_bake_asset_returns_full_pap():
    path = save_mesh_tmp(make_box(extents=(1.0, 1.0, 1.0)))
    pap = bake_asset("cube_01", path)
    assert isinstance(pap, PAP)
    assert pap.asset_id == "cube_01"
    assert pap.geometry.volume_m3 > 0
    assert pap.physical.mass_kg > 0
    assert pap.profile == "rigid_prop"


def test_bake_asset_default_material_when_none_authored():
    """No part_materials → every part is 'default' → density 1000."""
    path = save_mesh_tmp(make_box(extents=(1.0, 1.0, 1.0)))
    pap = bake_asset("cube_default", path)
    assert math.isclose(pap.physical.mass_kg, MATERIAL_DENSITY["default"], rel_tol=1e-2)


def test_bake_asset_locks_authored_material_fields():
    """Authored part_materials are recorded in provenance.locked."""
    path = save_mesh_tmp(make_box(extents=(1.0, 1.0, 1.0)))
    pap = bake_asset("cube_bronze", path, part_materials={0: "bronze"})
    assert any("material" in f for f in pap.provenance.locked)


def test_bake_asset_no_locked_fields_when_unauthored():
    path = save_mesh_tmp(make_box(extents=(1.0, 1.0, 1.0)))
    pap = bake_asset("cube_auto", path)
    assert pap.provenance.locked == []
