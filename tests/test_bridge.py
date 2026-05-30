"""
Headless tests for the UE5 Remote Control bridge (Task B5): `conscience/ue5/bridge.py`.

No Unreal, no C++, no GPU. `pytest-httpserver` stands up a fake Remote Control
endpoint; the bridge is exercised entirely against that mock. The contract under
test:

  * `sync_scene(selector)` GETs the tagged actors, converts UE5 -> canonical via the
    B1 adapter (x0.01 + negate-X mirror), and returns `[(actor_id, Transform), ...]`.
  * `commit(diff, expected_hash)` is concurrency-guarded: it re-reads the scene,
    hashes it, and raises `ConcurrencyError` (PUTting nothing) if the world changed
    under us; otherwise it PUTs the canonical->UE5 transform.
  * `snapshot_hash(actors)` is a stable, order-independent-ish hash of the synced set.
  * Commit-once discipline: one validated PUT, no live two-way loop.
"""

from __future__ import annotations

import json

import pytest

from conscience.ue5 import adapter
from conscience.ue5.bridge import ConcurrencyError, UE5Bridge
from contracts import Diff, Transform
from tests.helpers import mock_ue5_actor, mock_ue5_scene


# --------------------------------------------------------------------------- #
# Mock Remote Control wiring
# --------------------------------------------------------------------------- #
_SYNC_PATH = "/remote/actors"      # GET tagged actors
_COMMIT_PATH = "/remote/object/property"  # PUT a transform


def _serve_scene(httpserver, scene: dict):
    """Make the mock endpoint answer GET <_SYNC_PATH> with `scene` JSON."""
    httpserver.expect_request(_SYNC_PATH, method="GET").respond_with_json(scene)


def _bridge(httpserver) -> UE5Bridge:
    return UE5Bridge(base_url=httpserver.url_for("").rstrip("/"))


# --------------------------------------------------------------------------- #
# sync_scene: UE5 -> canonical conversion actually happened
# --------------------------------------------------------------------------- #
def test_sync_scene_returns_canonical_transforms(httpserver):
    _serve_scene(httpserver, mock_ue5_scene(1))
    bridge = _bridge(httpserver)

    actors = bridge.sync_scene("tag:plumb")

    assert len(actors) == 1
    actor_id, t = actors[0]
    assert actor_id == "Actor_0"
    assert isinstance(t, Transform)
    # UE5 location [-100, 200, 300] cm -> canonical [1, 2, 3] m (x0.01 + negate-X).
    assert t.pos == pytest.approx([1.0, 2.0, 3.0])


def test_sync_scene_applies_the_mirror_and_scale(httpserver):
    # An asymmetric location so the negate-X mirror is unambiguous.
    actor = mock_ue5_actor(actor_id="X", location_cm=(50.0, -30.0, 12.0))
    _serve_scene(httpserver, {"actors": [actor]})
    bridge = _bridge(httpserver)

    (_, t), = bridge.sync_scene("tag:plumb")

    # The bridge must route through the B1 adapter, not roll its own maths.
    assert t.pos == pytest.approx(adapter.ue5_to_canon_point([50.0, -30.0, 12.0]))
    # Spelled out: x negated + /100, y/z just /100.
    assert t.pos == pytest.approx([-0.5, -0.3, 0.12])


def test_sync_scene_converts_rotation_through_the_adapter(httpserver):
    actor = mock_ue5_actor(actor_id="X", rotation_quat=(0.1, 0.2, 0.3, 0.9))
    _serve_scene(httpserver, {"actors": [actor]})
    bridge = _bridge(httpserver)

    (_, t), = bridge.sync_scene("tag:plumb")

    assert t.quat == pytest.approx(adapter.ue5_to_canon_quat([0.1, 0.2, 0.3, 0.9]))


def test_sync_scene_returns_all_actors(httpserver):
    _serve_scene(httpserver, mock_ue5_scene(3))
    bridge = _bridge(httpserver)

    actors = bridge.sync_scene("tag:plumb")

    assert [aid for aid, _ in actors] == ["Actor_0", "Actor_1", "Actor_2"]


# --------------------------------------------------------------------------- #
# snapshot_hash: stable, change-sensitive
# --------------------------------------------------------------------------- #
def test_snapshot_hash_is_stable(httpserver):
    _serve_scene(httpserver, mock_ue5_scene(2))
    bridge = _bridge(httpserver)
    actors = bridge.sync_scene("tag:plumb")

    assert bridge.snapshot_hash(actors) == bridge.snapshot_hash(actors)


def test_snapshot_hash_changes_when_the_scene_changes(httpserver):
    bridge = UE5Bridge(base_url="http://unused")
    a = bridge._actors_from_json(mock_ue5_scene(1))
    moved = mock_ue5_scene(1)
    moved["actors"][0]["location"]["x"] = -999.0
    b = bridge._actors_from_json(moved)

    assert bridge.snapshot_hash(a) != bridge.snapshot_hash(b)


# --------------------------------------------------------------------------- #
# commit: PUTs the correct UE5-space payload when the hash matches
# --------------------------------------------------------------------------- #
def test_commit_puts_ue5_space_payload(httpserver):
    _serve_scene(httpserver, mock_ue5_scene(1))
    bridge = _bridge(httpserver)
    actors = bridge.sync_scene("tag:plumb")
    expected = bridge.snapshot_hash(actors)

    # Capture what the PUT body contains.
    httpserver.expect_request(_COMMIT_PATH, method="PUT").respond_with_json({"ok": True})

    diff = Diff(object="Actor_0", transform=Transform(pos=[1.0, 2.0, 3.0]))
    ok = bridge.commit(diff, expected_hash=expected)

    assert ok is True
    # One PUT happened, carrying the UE5-space (cm, mirrored) location.
    put_logs = [
        (req, resp) for req, resp in httpserver.log
        if req.method == "PUT" and req.path == _COMMIT_PATH
    ]
    assert len(put_logs) == 1
    body = json.loads(put_logs[0][0].get_data())
    # canonical [1,2,3] m -> UE5 [-100, 200, 300] cm. The PUT mirrors the read
    # shape: location as {x, y, z}.
    loc = body["location"]
    assert (loc["x"], loc["y"], loc["z"]) == pytest.approx((-100.0, 200.0, 300.0))
    # The targeted actor id rides along so UE5 knows which object to move.
    assert body["actorId"] == "Actor_0"


def test_commit_returns_true_on_matching_hash(httpserver):
    _serve_scene(httpserver, mock_ue5_scene(1))
    httpserver.expect_request(_COMMIT_PATH, method="PUT").respond_with_json({"ok": True})
    bridge = _bridge(httpserver)
    actors = bridge.sync_scene("tag:plumb")
    h = bridge.snapshot_hash(actors)

    diff = Diff(object="Actor_0", transform=Transform(pos=[0.0, 0.0, 0.5]))
    assert bridge.commit(diff, expected_hash=h) is True


# --------------------------------------------------------------------------- #
# Optimistic concurrency: a changed snapshot REFUSES the commit
# --------------------------------------------------------------------------- #
def test_commit_raises_concurrency_error_when_scene_changed(httpserver):
    # First sync to compute the "expected" hash...
    _serve_scene(httpserver, mock_ue5_scene(1))
    bridge = _bridge(httpserver)
    actors = bridge.sync_scene("tag:plumb")
    stale_hash = bridge.snapshot_hash(actors)

    # ...then the world moves under us: re-arm the GET to return a different scene.
    httpserver.clear_all_handlers()
    changed = mock_ue5_scene(1)
    changed["actors"][0]["location"]["x"] = -777.0
    _serve_scene(httpserver, changed)
    # A PUT handler exists but must never be hit.
    httpserver.expect_request(_COMMIT_PATH, method="PUT").respond_with_json({"ok": True})

    diff = Diff(object="Actor_0", transform=Transform(pos=[0.0, 0.0, 0.5]))
    with pytest.raises(ConcurrencyError):
        bridge.commit(diff, expected_hash=stale_hash)

    # And it did NOT PUT.
    put_logs = [r for r, _ in httpserver.log if r.method == "PUT"]
    assert put_logs == []


def test_commit_does_not_put_on_concurrency_failure(httpserver):
    _serve_scene(httpserver, mock_ue5_scene(1))
    bridge = _bridge(httpserver)
    actors = bridge.sync_scene("tag:plumb")

    httpserver.clear_all_handlers()
    changed = mock_ue5_scene(1)
    changed["actors"][0]["location"]["z"] = 1.0
    _serve_scene(httpserver, changed)
    httpserver.expect_request(_COMMIT_PATH, method="PUT").respond_with_json({"ok": True})

    with pytest.raises(ConcurrencyError):
        bridge.commit(
            Diff(object="Actor_0", transform=Transform(pos=[0.0, 0.0, 0.5])),
            expected_hash=bridge.snapshot_hash(actors),
        )
    assert [r for r, _ in httpserver.log if r.method == "PUT"] == []
