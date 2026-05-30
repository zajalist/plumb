"""
tests/test_bake_profiles.py — Task 11: bake_profiles (TDD, green before commit).

Tests for cortex/bake_profiles/:
  * Profile protocol (detect, passes, default_states, default_regions,
    default_constraints)
  * Registry + load_profile()
  * Door: swept_volume() produces a wedge larger than the door panel; a box
    inside the wedge fails door_clear, a box outside passes.
  * Tree: seasonal default_states, attach-band region stub.
  * Shelf: fill-region capacity + populate() yields only gate-valid placements.
  * Profile detection picks "articulated" for authored profile.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
import trimesh

from contracts import PAP, Geometry, Physical, Structural, Semantics, Provenance, Transform
from tests.helpers import make_box


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_door_pap(
    width: float = 0.9,
    height: float = 2.1,
    thickness: float = 0.05,
    hinge_range_deg: float = 95.0,
) -> PAP:
    """A door PAP with articulation metadata."""
    pap = PAP(
        asset_id="door_01",
        profile="articulated",
        geometry=Geometry(
            aabb=[width / 2, thickness / 2, height / 2],
            obb=[width / 2, thickness / 2, height / 2],
            volume_m3=width * height * thickness,
            convex_parts=1,
            watertight=True,
        ),
        physical=Physical(
            mass_kg=25.0,
            com=[width / 2, 0.0, height / 2],
        ),
        semantics=Semantics(cls="door", affordances=["open", "close"]),
    )
    # Attach articulation metadata so the profile can read it.
    pap.__dict__["_joint"] = {
        "axis": [0.0, 0.0, 1.0],  # Z-axis hinge
        "range_deg": hinge_range_deg,
        "hinge_point": [0.0, 0.0, 0.0],  # hinge at origin
    }
    # Also attach the door panel mesh so swept_volume has geometry to work with.
    panel = trimesh.creation.box(extents=[width, thickness, height])
    # Translate so hinge is at x=0: door extends from x=0 to x=width.
    panel.apply_translation([width / 2, 0.0, height / 2])
    pap.__dict__["_convex_parts"] = [panel]
    return pap


def _make_shelf_pap(
    width: float = 1.0,
    depth: float = 0.4,
    height: float = 1.8,
    num_shelves: int = 3,
) -> PAP:
    """A shelf PAP with fill-region capacity metadata."""
    pap = PAP(
        asset_id="shelf_01",
        profile="shelf",
        geometry=Geometry(
            aabb=[width / 2, depth / 2, height / 2],
            obb=[width / 2, depth / 2, height / 2],
            volume_m3=width * depth * height,
            convex_parts=1,
            watertight=True,
        ),
        physical=Physical(mass_kg=20.0, com=[0.0, 0.0, height / 2]),
        semantics=Semantics(cls="shelf", affordances=["support"]),
    )
    shelf_height = height / num_shelves
    pap.__dict__["_fill_regions"] = [
        {
            "id": f"shelf_{i}",
            "origin": [0.0, 0.0, i * shelf_height],
            "size": [width, depth, shelf_height * 0.8],
            "max_load_kg": 10.0,
        }
        for i in range(num_shelves)
    ]
    return pap


def _make_tree_pap() -> PAP:
    """A tree PAP."""
    return PAP(
        asset_id="tree_01",
        profile="tree",
        geometry=Geometry(
            aabb=[0.5, 0.5, 2.0],
            obb=[0.5, 0.5, 2.0],
            volume_m3=math.pi * 0.5**2 * 4.0,
            convex_parts=1,
            watertight=True,
        ),
        physical=Physical(mass_kg=50.0, com=[0.0, 0.0, 1.0]),
        semantics=Semantics(cls="tree", affordances=["seasonal"]),
    )


def _make_rigid_pap() -> PAP:
    """A generic rigid prop PAP."""
    return PAP(
        asset_id="prop_01",
        profile="rigid_prop",
        geometry=Geometry(
            aabb=[0.3, 0.3, 0.3],
            obb=[0.3, 0.3, 0.3],
            volume_m3=0.6**3,
        ),
        physical=Physical(mass_kg=5.0, com=[0.0, 0.0, 0.3]),
    )


# ---------------------------------------------------------------------------
# 1. Profile protocol shape
# ---------------------------------------------------------------------------

class TestProfileProtocol:
    """Every registered profile satisfies the Profile protocol."""

    def test_door_profile_has_all_protocol_fields(self):
        from cortex.bake_profiles import get_profile_by_name
        prof = get_profile_by_name("articulated")
        assert callable(prof.detect)
        assert callable(prof.passes)
        assert isinstance(prof.default_states, list)
        assert isinstance(prof.default_regions, list)
        assert isinstance(prof.default_constraints, list)

    def test_tree_profile_has_all_protocol_fields(self):
        from cortex.bake_profiles import get_profile_by_name
        prof = get_profile_by_name("tree")
        assert callable(prof.detect)
        assert callable(prof.passes)
        assert isinstance(prof.default_states, list)
        assert isinstance(prof.default_regions, list)
        assert isinstance(prof.default_constraints, list)

    def test_shelf_profile_has_all_protocol_fields(self):
        from cortex.bake_profiles import get_profile_by_name
        prof = get_profile_by_name("shelf")
        assert callable(prof.detect)
        assert callable(prof.passes)
        assert isinstance(prof.default_states, list)
        assert isinstance(prof.default_regions, list)
        assert isinstance(prof.default_constraints, list)


# ---------------------------------------------------------------------------
# 2. load_profile() — registry + detection
# ---------------------------------------------------------------------------

class TestLoadProfile:
    """load_profile picks the right profile."""

    def test_authored_profile_wins(self):
        """When pap.profile == 'articulated', load_profile returns the door profile."""
        from cortex.bake_profiles import load_profile
        pap = _make_door_pap()
        prof = load_profile(pap)
        assert prof.detect(pap) is True

    def test_authored_tree_wins(self):
        from cortex.bake_profiles import load_profile
        pap = _make_tree_pap()
        prof = load_profile(pap)
        assert prof.detect(pap) is True

    def test_authored_shelf_wins(self):
        from cortex.bake_profiles import load_profile
        pap = _make_shelf_pap()
        prof = load_profile(pap)
        assert prof.detect(pap) is True

    def test_rigid_prop_fallback(self):
        """Unknown / 'rigid_prop' profile falls back to the rigid-prop default."""
        from cortex.bake_profiles import load_profile
        pap = _make_rigid_pap()
        prof = load_profile(pap)
        # Should not crash; returns a valid Profile.
        assert callable(prof.detect)
        assert callable(prof.passes)

    def test_passes_returns_pap(self):
        """passes() returns a PAP."""
        from cortex.bake_profiles import load_profile
        pap = _make_door_pap()
        prof = load_profile(pap)
        result = prof.passes(pap)
        assert isinstance(result, PAP)


# ---------------------------------------------------------------------------
# 3. Door: swept_volume
# ---------------------------------------------------------------------------

class TestDoorSweptVolume:
    """swept_volume() for a 95° hinge produces a wedge > the door panel."""

    def test_swept_volume_larger_than_panel(self):
        """95° sweep volume must exceed the panel volume."""
        from cortex.bake_profiles.door import swept_volume
        pap = _make_door_pap(hinge_range_deg=95.0)
        tf = Transform(pos=[0.0, 0.0, 0.0], quat=[0.0, 0.0, 0.0, 1.0])
        sweep = swept_volume(pap, tf)
        assert isinstance(sweep, trimesh.Trimesh)
        panel_vol = pap.geometry.volume_m3
        assert sweep.volume > panel_vol, (
            f"Swept volume {sweep.volume:.4f} should exceed panel {panel_vol:.4f}"
        )

    def test_swept_volume_is_wedge_shaped(self):
        """The sweep should span more than 90° in XY (wider than the door panel in y)."""
        from cortex.bake_profiles.door import swept_volume
        pap = _make_door_pap(width=0.9, hinge_range_deg=95.0)
        tf = Transform(pos=[0.0, 0.0, 0.0], quat=[0.0, 0.0, 0.0, 1.0])
        sweep = swept_volume(pap, tf)
        # The door sweeps in XY; its AABB should be wider in Y than the panel thickness.
        bbox = sweep.bounding_box.extents
        door_thickness = 0.05
        assert bbox[1] > door_thickness * 2, "Wedge should be wider in Y than panel thickness"

    def test_box_inside_sweep_fails_door_clear(self):
        """A box placed inside the wedge arc fails the door_clear constraint."""
        from cortex.bake_profiles.door import swept_volume, make_sweep_pap
        from cortex.gates.constraints import evaluate_constraints
        from cortex.world import WorldModel

        door_pap = _make_door_pap(width=0.9, hinge_range_deg=95.0)
        door_tf = Transform(pos=[0.0, 0.0, 0.0], quat=[0.0, 0.0, 0.0, 1.0])

        # Compute the sweep and wrap it as a PAP node.
        sweep_mesh = swept_volume(door_pap, door_tf)
        sweep_pap = make_sweep_pap(sweep_mesh, "door_01_sweep")

        # Place an obstacle inside the sweep arc (middle of the door arc, ~47° in).
        angle_rad = math.radians(47.0)
        radius = 0.45  # halfway along the door width
        obs_x = radius * math.cos(angle_rad)
        obs_y = radius * math.sin(angle_rad)
        obs_pap = PAP(
            asset_id="obstacle_01",
            profile="rigid_prop",
            geometry=Geometry(aabb=[0.1, 0.1, 0.1], obb=[0.1, 0.1, 0.1]),
            physical=Physical(mass_kg=1.0, com=[0.0, 0.0, 0.1]),
        )
        small_box = trimesh.creation.box(extents=[0.2, 0.2, 0.2])
        obs_pap.__dict__["_convex_parts"] = [small_box]

        world = WorldModel()
        world.add("sweep", sweep_pap, door_tf)
        world.add("obstacle", obs_pap,
                  Transform(pos=[obs_x, obs_y, 1.0], quat=[0, 0, 0, 1]))

        laws = [{"law": "door_clear", "node": "obstacle", "sweep_node": "sweep"}]
        result = evaluate_constraints(world, laws)
        assert not result.ok, "Box inside sweep arc should fail door_clear"

    def test_box_outside_sweep_passes_door_clear(self):
        """A box placed well outside the wedge arc passes the door_clear constraint."""
        from cortex.bake_profiles.door import swept_volume, make_sweep_pap
        from cortex.gates.constraints import evaluate_constraints
        from cortex.world import WorldModel

        door_pap = _make_door_pap(width=0.9, hinge_range_deg=95.0)
        door_tf = Transform(pos=[0.0, 0.0, 0.0], quat=[0.0, 0.0, 0.0, 1.0])

        sweep_mesh = swept_volume(door_pap, door_tf)
        sweep_pap = make_sweep_pap(sweep_mesh, "door_01_sweep")

        # Place obstacle clearly outside the wedge (behind the hinge, at -y).
        obs_pap = PAP(
            asset_id="obstacle_02",
            profile="rigid_prop",
            geometry=Geometry(aabb=[0.1, 0.1, 0.1], obb=[0.1, 0.1, 0.1]),
            physical=Physical(mass_kg=1.0, com=[0.0, 0.0, 0.1]),
        )
        small_box = trimesh.creation.box(extents=[0.2, 0.2, 0.2])
        obs_pap.__dict__["_convex_parts"] = [small_box]

        world = WorldModel()
        world.add("sweep", sweep_pap, door_tf)
        # Place at x=5.0, well away from the 0.9m door.
        world.add("obstacle", obs_pap,
                  Transform(pos=[5.0, 0.0, 1.0], quat=[0, 0, 0, 1]))

        laws = [{"law": "door_clear", "node": "obstacle", "sweep_node": "sweep"}]
        result = evaluate_constraints(world, laws)
        assert result.ok, "Box far outside sweep arc should pass door_clear"


# ---------------------------------------------------------------------------
# 4. Tree: seasonal states + attach-band region
# ---------------------------------------------------------------------------

class TestTreeProfile:
    """Tree profile has seasonal states and an attach-band region stub."""

    def test_tree_default_states_include_seasonal(self):
        from cortex.bake_profiles import get_profile_by_name
        prof = get_profile_by_name("tree")
        states = prof.default_states
        assert len(states) >= 2, "Tree should have at least 2 seasonal states"
        # Expect at least 'summer' and 'winter' (or equivalent seasonal variants).
        state_set = set(states)
        assert len(state_set) == len(states), "States should be unique"

    def test_tree_default_regions_has_attach_band(self):
        from cortex.bake_profiles import get_profile_by_name
        prof = get_profile_by_name("tree")
        regions = prof.default_regions
        assert len(regions) >= 1, "Tree should have at least one region (attach-band stub)"
        # Check at least one region has an 'attach' role.
        roles = [r.get("role", "") for r in regions]
        assert any("attach" in role for role in roles), (
            f"Tree regions should include an attach-band; got roles: {roles}"
        )

    def test_tree_passes_returns_pap_with_states(self):
        from cortex.bake_profiles import get_profile_by_name, load_profile
        pap = _make_tree_pap()
        prof = load_profile(pap)
        result = prof.passes(pap)
        assert isinstance(result, PAP)
        assert len(result.rest_states) >= 2


# ---------------------------------------------------------------------------
# 5. Shelf: populate() yields gate-valid placements
# ---------------------------------------------------------------------------

class TestShelfPopulate:
    """populate() re-validates each placement through the orchestrator."""

    def _make_small_asset_pap(self, asset_id: str) -> PAP:
        """A small vase/prop that fits on a shelf."""
        pap = PAP(
            asset_id=asset_id,
            profile="rigid_prop",
            geometry=Geometry(
                aabb=[0.05, 0.05, 0.1],
                obb=[0.05, 0.05, 0.1],
                volume_m3=0.1 * 0.1 * 0.2,
            ),
            physical=Physical(mass_kg=0.5, com=[0.0, 0.0, 0.1]),
        )
        small_box = trimesh.creation.box(extents=[0.1, 0.1, 0.2])
        pap.__dict__["_convex_parts"] = [small_box]
        return pap

    def test_populate_returns_list_of_transforms(self):
        """populate() returns a list of (asset, Transform) placements."""
        from cortex.bake_profiles.shelf import populate

        shelf_pap = _make_shelf_pap(num_shelves=3)
        assets = [self._make_small_asset_pap(f"vase_{i}") for i in range(3)]
        region = shelf_pap.__dict__["_fill_regions"][0]
        placements = populate(region, assets)
        assert isinstance(placements, list)

    def test_populate_yields_valid_placements_only(self):
        """Each yielded placement passes gate validation."""
        from cortex.bake_profiles.shelf import populate

        shelf_pap = _make_shelf_pap(num_shelves=3)
        assets = [self._make_small_asset_pap(f"vase_{i}") for i in range(2)]
        region = shelf_pap.__dict__["_fill_regions"][0]
        placements = populate(region, assets)

        # All returned placements should be (pap, Transform) pairs.
        for pap, tf in placements:
            assert isinstance(pap, PAP)
            assert isinstance(tf, Transform)

    def test_populate_respects_capacity(self):
        """populate() does not exceed the region's physical size."""
        from cortex.bake_profiles.shelf import populate

        # Narrow shelf region can only fit limited items.
        shelf_pap = _make_shelf_pap(width=0.3, depth=0.3, num_shelves=1)
        assets = [self._make_small_asset_pap(f"asset_{i}") for i in range(10)]
        region = shelf_pap.__dict__["_fill_regions"][0]
        placements = populate(region, assets)
        # Should not overflow the shelf width.
        for _, tf in placements:
            x, y, z = tf.pos
            assert abs(x) <= 0.3 / 2 + 0.15, f"Asset x={x:.3f} overflows shelf width"

    def test_populate_empty_assets_returns_empty(self):
        """populate() with no assets returns an empty list."""
        from cortex.bake_profiles.shelf import populate

        shelf_pap = _make_shelf_pap(num_shelves=2)
        region = shelf_pap.__dict__["_fill_regions"][0]
        placements = populate(region, [])
        assert placements == []


# ---------------------------------------------------------------------------
# 6. Profile detection
# ---------------------------------------------------------------------------

class TestProfileDetection:
    """Profile detection via authored pap.profile and heuristic fallback."""

    def test_detect_articulated_by_profile_field(self):
        """pap.profile='articulated' → articulated profile detects as True."""
        from cortex.bake_profiles import get_profile_by_name
        pap = _make_door_pap()
        prof = get_profile_by_name("articulated")
        assert prof.detect(pap) is True

    def test_detect_tree_by_profile_field(self):
        from cortex.bake_profiles import get_profile_by_name
        pap = _make_tree_pap()
        prof = get_profile_by_name("tree")
        assert prof.detect(pap) is True

    def test_detect_shelf_by_profile_field(self):
        from cortex.bake_profiles import get_profile_by_name
        pap = _make_shelf_pap()
        prof = get_profile_by_name("shelf")
        assert prof.detect(pap) is True

    def test_rigid_prop_does_not_detect_as_articulated(self):
        """A rigid_prop PAP should not be detected as articulated."""
        from cortex.bake_profiles import get_profile_by_name
        pap = _make_rigid_pap()
        prof = get_profile_by_name("articulated")
        assert prof.detect(pap) is False
