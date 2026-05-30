"""
The 4-minute beat, end to end (Task B7) — `conscience/demo.py`.

This is the orchestration script that ties the whole conscience together: it drives
the agent loop over the Gallery scene and, for every step, renders the verdict into a
Rerun recording so the timeline scrubs the demo beat —

    placed by vibes  ->  topple   (red bbox + ghost candidate + fix arrow)
    after the nudge  ->  repaired (all green)

and then prints the portable `.wdf` document as the kicker (`export_wdf`).

Swappable by one line
---------------------
`run_demo` takes any `CortexClient`. Today it runs on the fixtures-backed
`FakeCortex` (no MCP, no Unreal — fully headless); the day Person A's MCP server
lands, passing a real `McpCortex` is the only change. The loop, the renderer and the
`.wdf` export never move.

Pure consumer of the contract
-----------------------------
Everything drawn is read straight out of the `Verdict` / `PAP` / `Transform` — no
physics is computed here and `cortex/` is never imported. The conscience renders
truth; it does not compute it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

import fixtures
from contracts import PAP, Transform, Verdict
from conscience import rerun_viz
from conscience.agent_loop import Step, run_episode
from conscience.cortex_client import CortexClient, FakeCortex
from conscience.wdf import (
    Asset,
    Field,
    Joint,
    Law,
    Placement,
    Scene,
    Vocabulary,
    WdfDocument,
    dumps,
)

# The renderer seam: `draw_verdict(rec, pap, transform, verdict)`. Defaulted so the
# demo "just renders", overridable so a test can spy on what was drawn per step.
DrawFn = Callable[..., None]

# Where the recording lands when the caller doesn't care to name it.
_DEFAULT_OUT = "gallery.rrd"


# --------------------------------------------------------------------------- #
# The Gallery scene — the single source of truth the demo runs on.
#
# It is BOTH the scene the agent loop drives (`selector` / `object` / `initial`
# transform, read by `agent_loop.ScriptedProposer`) AND the scene `export_wdf`
# describes as portable `.wdf`. One dict, two readers.
# --------------------------------------------------------------------------- #
GALLERY_SCENE: dict = {
    "selector": "tag:plumb",
    "object": "bronze_figure_03",
    # Placed "by vibes" too close to the pedestal edge -> topples (spec §15 step 5).
    "initial": Transform(pos=[0.0, 0.0, 0.40], quat=[0, 0, 0, 1]),
}

# The hero asset, drawn for every step. The conscience renders the same PAP the
# cortex reasoned over; only the transform (and verdict) change between steps.
_HERO: PAP = fixtures.BRONZE_FIGURE


# --------------------------------------------------------------------------- #
# Result — what `run_demo` hands back so a caller (or a test) can inspect the run.
# --------------------------------------------------------------------------- #
@dataclass
class DemoResult:
    """
    The outcome of a demo run: where the recording landed, the scrubbable step
    trail (topple then repair), and the final verdict the episode settled on.

    `final_verdict` is the verdict of the last step — green when the beat repaired,
    which the demo always does on the fixtures-backed cortex.
    """

    out: str
    steps: list[Step] = field(default_factory=list)
    final_verdict: Optional[Verdict] = None


# --------------------------------------------------------------------------- #
# run_demo — the whole beat, rendered.
# --------------------------------------------------------------------------- #
def run_demo(
    client: Optional[CortexClient] = None,
    out: str = _DEFAULT_OUT,
    *,
    scene: Optional[dict] = None,
    draw_fn: Optional[DrawFn] = None,
) -> DemoResult:
    """
    Run the Gallery beat end to end and render every step into a `.rrd` recording.

    1. Drive the agent loop (`run_episode`) over `scene` — it proposes the toppling
       placement, reads the failing verdict's diagnostics, asks the cortex for the
       recovery nudge, re-validates to green and commits (exactly once, only green).
    2. For each resulting `Step`, draw its verdict into the recording so the timeline
       scrubs topple (red bbox + ghost candidate + fix arrow) -> repair (green).
    3. Return a `DemoResult` with the recording path, the step trail and the final
       (green) verdict.

    `client` defaults to a fixtures-backed `FakeCortex` — the demo runs with zero
    arguments and zero external services. Swapping in a real `McpCortex` is the only
    line that changes. `draw_fn` defaults to `rerun_viz.draw_verdict`; it is a seam so
    a test can observe exactly what gets drawn for each step.
    """
    if client is None:
        client = FakeCortex()
    if scene is None:
        scene = GALLERY_SCENE
    draw = draw_fn if draw_fn is not None else rerun_viz.draw_verdict

    rec = rerun_viz.init_recording(out)

    steps = run_episode(client, scene)

    # Render every step — the failing one (so red / ghost / fix arrow show) AND the
    # passing one (so the scrub reaches green). The drawn transform is the proposal's:
    # where the agent put the asset for that attempt.
    for step in steps:
        draw(rec, _HERO, step.proposal.transform, step.verdict)

    # Flush the recording to disk so the `.rrd` is non-empty before we return.
    del rec

    final = steps[-1].verdict if steps else None
    return DemoResult(out=out, steps=steps, final_verdict=final)


# --------------------------------------------------------------------------- #
# export_wdf — the kicker: the scene as portable, parseable `.wdf` text.
# --------------------------------------------------------------------------- #
def _gallery_document() -> WdfDocument:
    """
    The Gallery as a `.wdf` document: the bronze figure (rigid prop, top-heavy) and
    the oak door (articulated, swept keep-clear), placed under the laws the gates
    enforce — the hard `stable` law (the bet), a soft `facing` aesthetic, and the
    hard `door_clear` swept-volume law — inside an `autumn` field.

    This is the same running example the `.wdf` task round-trips; `export_wdf` renders
    it with `dumps`, and `wdf.loads` reads it straight back.
    """
    bronze = Asset(
        name="bronze_figure",
        profile="rigid_prop",
        material={"body": "bronze"},
        states=["upright", "fell"],
        affordances=["base_contact"],
    )
    oak_door = Asset(
        name="oak_door",
        profile="articulated",
        joint=Joint(axis="hinge", range_min=0.0, range_max=95.0),
        swept_volume="keep_clear",
    )
    scene = Scene(
        name="the_gallery",
        fields=[Field(key="season", value="autumn")],
        placements=[
            Placement(asset="bronze_figure", preposition="on", target="pedestal",
                      state="upright"),
            Placement(asset="oak_door", preposition="at", target="north_wall"),
        ],
        laws=[
            Law(name="stable", expr="com_over_base(margin >= 2cm)", hard=True),
            Law(name="facing", expr="bronze.front -> entrance(<= 8deg)", hard=False),
            Law(name="door_clear", expr="keep_clear(oak_door.swept)", hard=True),
        ],
    )
    return WdfDocument(vocabulary=Vocabulary(assets=[bronze, oak_door]), scene=scene)


def export_wdf(scene: dict = GALLERY_SCENE) -> str:
    """
    Render the demo scene as portable `.wdf` text — the kicker after the 3D beat.

    The `scene` argument keeps the signature the plan names; the demo only ever runs
    the one Gallery scene, so the returned text is the Gallery document. The result is
    guaranteed parseable: `wdf.loads(export_wdf(...))` reads it straight back into a
    `WdfDocument`, which is the proof `.wdf` is a real, round-trippable language.
    """
    return dumps(_gallery_document())
