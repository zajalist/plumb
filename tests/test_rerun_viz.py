"""
Headless tests for the 3D conscience (Task B2): `conscience/rerun_viz.py`.

Everything runs WITHOUT a GPU and WITHOUT the Rerun viewer: we log to a `.rrd`
file via `rr.RecordingStream` + `rr.save(...)` and assert on the file plus a thin
logging spy. The spy captures every `(entity_path, entity)` pair `draw_verdict`
logs, so we can read the bbox color (green pass / amber soft / red hard-fail) and
prove the ghost-topple + fix arrow appear exactly when the verdict calls for them.

`draw_verdict` is a PURE CONSUMER of the contract: it renders from the Verdict
JSON + PAP + Transform alone — no physics, no cortex import.
"""

from __future__ import annotations

import os

import rerun as rr

import fixtures
from contracts import Transform
from conscience import rerun_viz
from tests.helpers import tmp_path


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _decode_colors(entity) -> list[tuple[int, int, int, int]]:
    """Read the packed RGBA colors off any logged Rerun entity (RRRRGGGGBBBBAAAA)."""
    if getattr(entity, "colors", None) is None:
        return []
    out = []
    for v in entity.colors.as_arrow_array().to_pylist():
        out.append(((v >> 24) & 0xFF, (v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF))
    return out


class LogSpy:
    """A thin stand-in for `rec.log` that records what would be logged."""

    def __init__(self):
        self.calls: list[tuple[str, object]] = []

    def __call__(self, entity_path, entity, *extra, **kwargs):
        self.calls.append((entity_path, entity))

    def by_suffix(self, suffix: str):
        return [(p, e) for (p, e) in self.calls if p.split("/")[-1] == suffix]

    def paths(self) -> list[str]:
        return [p for (p, _) in self.calls]


_T = Transform(pos=[0.30, -0.20, 0.40], quat=[0, 0, 0, 1], scale=[1, 1, 1])


# --------------------------------------------------------------------------- #
# init_recording
# --------------------------------------------------------------------------- #
def test_init_recording_returns_stream_and_sets_right_hand_z_up():
    spy = LogSpy()
    path = tmp_path(".rrd")
    rec = rerun_viz.init_recording(path, log_fn=spy)
    assert isinstance(rec, rr.RecordingStream)
    # The canonical-space root must carry an explicit RIGHT_HAND_Z_UP view-coords
    # so a silent handedness flip is caught. (RIGHT_HAND_Z_UP is a ViewCoordinates
    # *component* whose `==` is element-wise, hence the `.all()`.)
    want = rr.ViewCoordinates.RIGHT_HAND_Z_UP
    vc_calls = [(p, e) for (p, e) in spy.calls if type(e) is type(want)]
    assert len(vc_calls) == 1
    path_logged, vc = vc_calls[0]
    assert path_logged == rerun_viz.ROOT
    assert (vc == want).all()


# --------------------------------------------------------------------------- #
# draw_verdict writes a non-empty .rrd (the headline headless guarantee)
# --------------------------------------------------------------------------- #
def test_draw_topple_then_repaired_write_nonempty_rrd():
    for verdict in (fixtures.VERDICT_TOPPLE, fixtures.VERDICT_REPAIRED):
        path = tmp_path(".rrd")
        rec = rerun_viz.init_recording(path)
        rerun_viz.draw_verdict(rec, fixtures.BRONZE_FIGURE, _T, verdict)
        # flush by dropping the stream, then assert the file is non-empty.
        del rec
        assert os.path.exists(path)
        assert os.path.getsize(path) > 0


def test_draw_verdict_runs_without_error_on_both_fixtures():
    # No exception escapes for either the failing or the passing verdict.
    for verdict in (fixtures.VERDICT_TOPPLE, fixtures.VERDICT_REPAIRED):
        rec = rerun_viz.init_recording(tmp_path(".rrd"))
        rerun_viz.draw_verdict(rec, fixtures.BRONZE_FIGURE, _T, verdict)


# --------------------------------------------------------------------------- #
# Color: red for the failing gate, green for the passing one
# --------------------------------------------------------------------------- #
def test_bbox_is_red_on_hard_fail():
    spy = LogSpy()
    rec = rerun_viz.init_recording(tmp_path(".rrd"), log_fn=spy)
    rerun_viz.draw_verdict(rec, fixtures.BRONZE_FIGURE, _T,
                           fixtures.VERDICT_TOPPLE, log_fn=spy)
    bbox = spy.by_suffix("bbox")
    assert len(bbox) == 1
    (r, g, b, _a) = _decode_colors(bbox[0][1])[0]
    assert r > 150 and g < 100 and b < 100  # red-dominant


def test_bbox_is_green_on_pass():
    spy = LogSpy()
    rec = rerun_viz.init_recording(tmp_path(".rrd"), log_fn=spy)
    rerun_viz.draw_verdict(rec, fixtures.BRONZE_FIGURE, _T,
                           fixtures.VERDICT_REPAIRED, log_fn=spy)
    bbox = spy.by_suffix("bbox")
    assert len(bbox) == 1
    (r, g, b, _a) = _decode_colors(bbox[0][1])[0]
    assert g > 150 and r < 100  # green-dominant


def test_bbox_is_amber_on_soft_only_fail():
    # A verdict that passes every hard gate but carries soft cost -> amber, not red/green.
    soft = fixtures.VERDICT_REPAIRED.model_copy(update={"soft_cost": 1.5})
    spy = LogSpy()
    rec = rerun_viz.init_recording(tmp_path(".rrd"), log_fn=spy)
    rerun_viz.draw_verdict(rec, fixtures.BRONZE_FIGURE, _T, soft, log_fn=spy)
    (r, g, b, _a) = _decode_colors(spy.by_suffix("bbox")[0][1])[0]
    assert r > 150 and g > 100 and b < 100  # amber (high R, mid/high G, low B)


# --------------------------------------------------------------------------- #
# CoM marker, support polygon, gravity arrow are always drawn
# --------------------------------------------------------------------------- #
def test_com_marker_logged_at_world_transformed_com():
    spy = LogSpy()
    rec = rerun_viz.init_recording(tmp_path(".rrd"), log_fn=spy)
    rerun_viz.draw_verdict(rec, fixtures.BRONZE_FIGURE, _T,
                           fixtures.VERDICT_TOPPLE, log_fn=spy)
    com = spy.by_suffix("com")
    assert len(com) == 1
    pts = com[0][1].positions.as_arrow_array().to_pylist()
    # local com [0, 0.04, 0.71] + translate [0.30, -0.20, 0.40] (identity rot/scale)
    px, py, pz = pts[0]
    assert abs(px - 0.30) < 1e-6
    assert abs(py - (-0.20 + 0.04)) < 1e-6
    assert abs(pz - (0.40 + 0.71)) < 1e-6


def test_support_polygon_and_gravity_always_present():
    spy = LogSpy()
    rec = rerun_viz.init_recording(tmp_path(".rrd"), log_fn=spy)
    rerun_viz.draw_verdict(rec, fixtures.BRONZE_FIGURE, _T,
                           fixtures.VERDICT_REPAIRED, log_fn=spy)
    assert len(spy.by_suffix("support")) == 1
    grav = spy.by_suffix("gravity")
    assert len(grav) == 1
    vecs = grav[0][1].vectors.as_arrow_array().to_pylist()
    # gravity points straight down (-Z) in canonical space.
    gx, gy, gz = vecs[0]
    assert gz < 0
    assert abs(gx) < 1e-6 and abs(gy) < 1e-6


# --------------------------------------------------------------------------- #
# Ghost + fix arrow: present IFF a gate has a fix
# --------------------------------------------------------------------------- #
def test_fix_arrow_and_ghost_present_on_stability_fail():
    spy = LogSpy()
    rec = rerun_viz.init_recording(tmp_path(".rrd"), log_fn=spy)
    rerun_viz.draw_verdict(rec, fixtures.BRONZE_FIGURE, _T,
                           fixtures.VERDICT_TOPPLE, log_fn=spy)
    assert len(spy.by_suffix("ghost")) == 1, "toppled candidate ghost must be drawn"
    fix = spy.by_suffix("fix")
    assert len(fix) == 1, "fix arrow must be drawn when a gate has a fix"
    vecs = fix[0][1].vectors.as_arrow_array().to_pylist()
    # The stability gate's fix.translate is [0.06, 0.0, 0.0].
    fx, fy, fz = vecs[0]
    assert abs(fx - 0.06) < 1e-6 and abs(fy) < 1e-6 and abs(fz) < 1e-6


def test_no_fix_arrow_when_all_gates_pass():
    spy = LogSpy()
    rec = rerun_viz.init_recording(tmp_path(".rrd"), log_fn=spy)
    rerun_viz.draw_verdict(rec, fixtures.BRONZE_FIGURE, _T,
                           fixtures.VERDICT_REPAIRED, log_fn=spy)
    assert spy.by_suffix("fix") == [], "no fix arrow when nothing needs fixing"
    assert spy.by_suffix("ghost") == [], "no ghost when stability passes"


def test_pure_consumer_does_not_import_cortex():
    # The conscience renders from the contract only — no cortex dependency.
    import sys
    assert not any(m == "cortex" or m.startswith("cortex.") for m in sys.modules), \
        "rerun_viz must never pull in cortex internals"
