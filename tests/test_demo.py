"""
Tests for the 4-minute demo beat (Task B7): `conscience/demo.py`.

`run_demo` ties the whole conscience together — it drives the agent loop over the
Gallery scene and, for every step, renders the verdict into a Rerun `.rrd` recording
so the timeline scrubs topple (red, ghost, fix arrow) -> repair (green). `export_wdf`
prints the portable `.wdf` document as the kicker.

Everything is HEADLESS: the recording streams to a `.rrd` file (no GPU, no viewer),
the cortex is the fixtures-backed `FakeCortex` (no MCP, no Unreal), and the whole
thing is a pure consumer of the contract — `cortex/` is never imported.
"""

from __future__ import annotations

import os
import sys

from conscience import demo
from conscience.cortex_client import FakeCortex
from conscience.wdf import loads
from tests.helpers import tmp_path


# --------------------------------------------------------------------------- #
# run_demo: produces a non-empty .rrd and ends on a green verdict.
# --------------------------------------------------------------------------- #
def test_run_demo_writes_nonempty_rrd():
    out = tmp_path(".rrd")
    demo.run_demo(client=FakeCortex(), out=out)
    assert os.path.exists(out)
    assert os.path.getsize(out) > 0


def test_run_demo_ends_on_green_verdict():
    result = demo.run_demo(client=FakeCortex(), out=tmp_path(".rrd"))
    # The episode ends repaired: the final verdict is green and was committed.
    assert result.final_verdict.ok is True
    assert result.steps[-1].verdict.ok is True
    assert result.steps[-1].committed is True


def test_run_demo_records_topple_then_repair():
    # The canonical demo beat is exactly two steps: a fail then a pass.
    result = demo.run_demo(client=FakeCortex(), out=tmp_path(".rrd"))
    assert len(result.steps) == 2
    assert result.steps[0].verdict.ok is False   # topple
    assert result.steps[1].verdict.ok is True    # repair


def test_run_demo_defaults_to_fakecortex_and_an_out_path():
    # Callable with zero arguments — the demo "just runs" on the fake cortex.
    result = demo.run_demo()
    assert result.final_verdict.ok is True
    assert os.path.exists(result.out)
    assert os.path.getsize(result.out) > 0


def test_run_demo_commits_exactly_once_and_only_when_green():
    client = FakeCortex()
    demo.run_demo(client=client, out=tmp_path(".rrd"))
    # Commit-once discipline: a single commit, and it was the green proposal.
    assert len(client.committed) == 1


# --------------------------------------------------------------------------- #
# run_demo draws every step into the recording (topple AND repair are rendered).
# --------------------------------------------------------------------------- #
def test_run_demo_draws_each_step_into_the_recording():
    drawn: list = []

    def spy_draw(rec, pap, transform, verdict, **kwargs):
        drawn.append(verdict)

    result = demo.run_demo(client=FakeCortex(), out=tmp_path(".rrd"),
                           draw_fn=spy_draw)
    # One draw per step: the failing verdict (so the red/ghost/fix render) AND the
    # passing one (so the timeline can scrub all the way to green).
    assert len(drawn) == len(result.steps) == 2
    assert drawn[0].ok is False
    assert drawn[1].ok is True


# --------------------------------------------------------------------------- #
# export_wdf: parseable portable .wdf, the kicker.
# --------------------------------------------------------------------------- #
def test_export_wdf_returns_parseable_text():
    text = demo.export_wdf(demo.GALLERY_SCENE)
    doc = loads(text)  # must not raise
    assert doc.scene is not None


def test_export_wdf_describes_the_gallery():
    text = demo.export_wdf(demo.GALLERY_SCENE)
    doc = loads(text)
    names = {a.name for a in doc.vocabulary.assets}
    assert "bronze_figure" in names
    # the stability law (the bet) survives the export round-trip
    law_names = {law.name for law in doc.scene.laws}
    assert "stable" in law_names


def test_export_wdf_round_trips_through_the_language():
    # Re-serialising the parsed export is stable: it really is the .wdf language.
    from conscience.wdf import dumps
    text = demo.export_wdf(demo.GALLERY_SCENE)
    assert dumps(loads(text)) == dumps(loads(dumps(loads(text))))


# --------------------------------------------------------------------------- #
# Pure consumer: the demo never reaches into cortex internals.
# --------------------------------------------------------------------------- #
def test_demo_does_not_import_cortex():
    # Run the full demo in a FRESH interpreter and confirm cortex never enters sys.modules.
    # Subprocess isolation keeps this honest when the cortex suite runs in the same session.
    from tests.helpers import cortex_modules_after
    setup = (
        "import tempfile\n"
        "from conscience import demo\n"
        "from conscience.cortex_client import FakeCortex\n"
        "demo.run_demo(client=FakeCortex(), "
        "out=tempfile.NamedTemporaryFile(suffix='.rrd', delete=False).name)\n"
    )
    assert cortex_modules_after(setup) == [], \
        "demo must render from the contract only — never import cortex internals"
