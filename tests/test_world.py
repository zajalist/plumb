"""
Tests for cortex/world.py — the pure-state world model (Task 1).

The world model is the optimistic-concurrency guard for commit: its
snapshot_hash() must be stable across insertion order and round-trip equal for
identical states, and must change when a transform (or the set of nodes) changes.
No physics here — this is pure state.
"""

from __future__ import annotations

import pytest

from contracts import PAP, Transform
from cortex.world import WorldModel, WorldNode


def _pap(asset_id: str = "asset_a", bake_version: int = 1) -> PAP:
    return PAP(asset_id=asset_id, bake_version=bake_version)


def _t(pos=(0.0, 0.0, 0.0)) -> Transform:
    return Transform(pos=list(pos))


def test_add_get_round_trips():
    w = WorldModel()
    pap = _pap("bronze_figure_03")
    t = _t((1.0, 2.0, 3.0))
    w.add("n1", pap, t)
    node = w.get("n1")
    assert isinstance(node, WorldNode)
    assert node.pap.asset_id == "bronze_figure_03"
    assert node.transform.pos == [1.0, 2.0, 3.0]
    assert node.parent is None


def test_add_with_parent_is_stored():
    w = WorldModel()
    w.add("root", _pap(), _t())
    w.add("child", _pap("asset_b"), _t((1, 0, 0)), parent="root")
    assert w.get("child").parent == "root"


def test_nodes_lists_all_node_ids():
    w = WorldModel()
    w.add("a", _pap(), _t())
    w.add("b", _pap("asset_b"), _t())
    assert sorted(w.nodes()) == ["a", "b"]


def test_get_missing_raises():
    w = WorldModel()
    with pytest.raises(KeyError):
        w.get("nope")


def test_add_duplicate_raises():
    w = WorldModel()
    w.add("a", _pap(), _t())
    with pytest.raises(KeyError):
        w.add("a", _pap(), _t())


def test_update_transform_changes_node_and_hash():
    w = WorldModel()
    w.add("a", _pap(), _t((0, 0, 0)))
    h0 = w.snapshot_hash()
    w.update_transform("a", _t((1, 0, 0)))
    assert w.get("a").transform.pos == [1.0, 0.0, 0.0]
    assert w.snapshot_hash() != h0


def test_update_missing_raises():
    w = WorldModel()
    with pytest.raises(KeyError):
        w.update_transform("ghost", _t())


def test_identical_states_hash_equal():
    w1 = WorldModel()
    w1.add("a", _pap("asset_a"), _t((1, 2, 3)))
    w1.add("b", _pap("asset_b", bake_version=2), _t((4, 5, 6)))

    w2 = WorldModel()
    w2.add("a", _pap("asset_a"), _t((1, 2, 3)))
    w2.add("b", _pap("asset_b", bake_version=2), _t((4, 5, 6)))

    assert w1.snapshot_hash() == w2.snapshot_hash()


def test_insertion_order_does_not_change_hash():
    w1 = WorldModel()
    w1.add("a", _pap("asset_a"), _t((1, 2, 3)))
    w1.add("b", _pap("asset_b"), _t((4, 5, 6)))

    w2 = WorldModel()
    w2.add("b", _pap("asset_b"), _t((4, 5, 6)))
    w2.add("a", _pap("asset_a"), _t((1, 2, 3)))

    assert w1.snapshot_hash() == w2.snapshot_hash()


def test_remove_is_reflected_in_nodes_and_hash():
    w = WorldModel()
    w.add("a", _pap(), _t())
    w.add("b", _pap("asset_b"), _t())
    h_before = w.snapshot_hash()
    w.remove("a")
    assert "a" not in w.nodes()
    assert w.nodes() == ["b"]
    assert w.snapshot_hash() != h_before


def test_remove_missing_raises():
    w = WorldModel()
    with pytest.raises(KeyError):
        w.remove("nope")


def test_hash_depends_on_asset_id_and_bake_version():
    w1 = WorldModel()
    w1.add("a", _pap("asset_a", bake_version=1), _t())

    w2 = WorldModel()
    w2.add("a", _pap("asset_a", bake_version=2), _t())
    assert w1.snapshot_hash() != w2.snapshot_hash()

    w3 = WorldModel()
    w3.add("a", _pap("asset_z", bake_version=1), _t())
    assert w1.snapshot_hash() != w3.snapshot_hash()


def test_hash_is_hex_sha256_string():
    w = WorldModel()
    w.add("a", _pap(), _t())
    h = w.snapshot_hash()
    assert isinstance(h, str)
    assert len(h) == 64
    int(h, 16)  # raises if not hex


def test_tiny_subtolerance_transform_change_hashes_equal():
    """Transforms are rounded before hashing, so sub-rounding jitter is invisible."""
    w1 = WorldModel()
    w1.add("a", _pap(), _t((1.0, 0.0, 0.0)))

    w2 = WorldModel()
    w2.add("a", _pap(), _t((1.0 + 1e-9, 0.0, 0.0)))

    assert w1.snapshot_hash() == w2.snapshot_hash()
