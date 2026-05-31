"""
Headless tests for the driver (Task B4): `conscience/cortex_client.py` +
`conscience/agent_loop.py`.

The whole demo beat — topple then repair — is driven WITHOUT a cortex, a GPU, or
an LLM: a `FakeCortex` (backed by `fixtures.py`) plays the part of Person A's MCP
server, and a `ScriptedProposer` plays the part of the agent. The loop is the swap
point: a real `McpCortex` and a real-LLM proposer drop in behind the same
`CortexClient` / `Proposer` interfaces with zero changes here.

The four invariants under test:
  1. `run_episode` ends on a GREEN verdict.
  2. it records exactly the topple -> repair step sequence.
  3. it NEVER calls `commit` before the verdict is green.
  4. structured diagnostics read off `VERDICT_TOPPLE` name the stability gate + its
     fix vector (the loop reads *which gate, what number, which way* — never a bare no).
"""

from __future__ import annotations

import fixtures
from contracts import Diff, GateName, Transform, Verdict
from conscience.agent_loop import ScriptedProposer, read_diagnostics, run_episode
from conscience.cortex_client import CortexClient, FakeCortex

# A minimal scene the loop syncs: one object placed "by vibes" near the edge.
_SCENE = {
    "selector": "tag:plumb",
    "object": "bronze_figure_03",
    "initial": Transform(pos=[0.0, 0.0, 0.40], quat=[0, 0, 0, 1]),
}


# --------------------------------------------------------------------------- #
# FakeCortex: the fixtures-backed stand-in for Person A's MCP server.
# --------------------------------------------------------------------------- #
def test_fake_cortex_satisfies_the_protocol():
    fake = FakeCortex()
    assert isinstance(fake, CortexClient)


def test_first_validate_topples_then_repaired_after_suggested_fix():
    fake = FakeCortex()
    bad = Diff(object="bronze_figure_03",
               transform=Transform(pos=[0.0, 0.0, 0.40]))
    v1 = fake.validate_operation(bad)
    assert v1.ok is False
    assert v1.stopped_at == GateName.stability
    assert v1 == fixtures.VERDICT_TOPPLE

    # Apply the cortex's own suggested transform -> the repaired (green) verdict.
    fixed = fake.suggest_transform("bronze_figure_03", {"goal": "stable"})
    v2 = fake.validate_operation(Diff(object="bronze_figure_03", transform=fixed))
    assert v2.ok is True
    assert v2 == fixtures.VERDICT_REPAIRED


def test_suggest_transform_returns_the_fixture_fix():
    fake = FakeCortex()
    t = fake.suggest_transform("bronze_figure_03", {"goal": "stable"})
    assert isinstance(t, Transform)
    assert t == fixtures.SUGGESTED_FIX


def test_sync_scene_returns_the_objects():
    fake = FakeCortex(objects=["bronze_figure_03", "oak_door"])
    ids = fake.sync_scene("tag:plumb")
    assert ids == ["bronze_figure_03", "oak_door"]


def test_commit_only_succeeds_on_a_validated_green_transform():
    fake = FakeCortex()
    good = Diff(object="bronze_figure_03", transform=fixtures.SUGGESTED_FIX)
    assert fake.commit(good) is True


# --------------------------------------------------------------------------- #
# read_diagnostics: never a bare 'no' — which gate, what number, which way.
# --------------------------------------------------------------------------- #
def test_read_diagnostics_off_topple_names_stability_gate_and_fix():
    diag = read_diagnostics(fixtures.VERDICT_TOPPLE)
    assert diag is not None
    assert diag.gate == GateName.stability
    assert diag.value_m == -0.07                 # CoM 7cm outside the polygon
    assert diag.fix.translate == [0.06, 0.0, 0.0]  # the way back to safe


def test_read_diagnostics_returns_none_on_a_green_verdict():
    assert read_diagnostics(fixtures.VERDICT_REPAIRED) is None


# --------------------------------------------------------------------------- #
# run_episode: the whole beat, end to end.
# --------------------------------------------------------------------------- #
def test_run_episode_ends_green():
    steps = run_episode(FakeCortex(), _SCENE, proposer=ScriptedProposer())
    assert steps[-1].verdict.ok is True
    assert steps[-1].verdict == fixtures.VERDICT_REPAIRED


def test_run_episode_records_exactly_topple_then_repair():
    steps = run_episode(FakeCortex(), _SCENE, proposer=ScriptedProposer())
    assert len(steps) == 2
    # step 0 = the topple, step 1 = the repair.
    assert steps[0].verdict == fixtures.VERDICT_TOPPLE
    assert steps[0].verdict.ok is False
    assert steps[1].verdict == fixtures.VERDICT_REPAIRED
    assert steps[1].verdict.ok is True
    # each step is a (proposal, verdict) pair the timeline can scrub.
    assert isinstance(steps[0].proposal, Diff)
    assert isinstance(steps[1].proposal, Diff)


def test_run_episode_never_commits_before_green():
    fake = FakeCortex()
    run_episode(fake, _SCENE, proposer=ScriptedProposer())
    # commit happens exactly once, and only after a green verdict was seen.
    assert len(fake.committed) == 1
    # the committed diff is the repaired (green) transform, not the toppling one.
    assert fake.committed[0].transform == fixtures.SUGGESTED_FIX


def test_run_episode_committed_flag_on_final_step_only():
    steps = run_episode(FakeCortex(), _SCENE, proposer=ScriptedProposer())
    assert steps[0].committed is False
    assert steps[-1].committed is True


def test_run_episode_uses_suggested_transform_for_the_repair():
    # The repair proposal is the cortex's suggest_transform output, not a re-guess.
    steps = run_episode(FakeCortex(), _SCENE, proposer=ScriptedProposer())
    assert steps[1].proposal.transform == fixtures.SUGGESTED_FIX


def test_run_episode_is_pure_consumer_no_cortex_import():
    # Run a full episode in a FRESH interpreter and confirm cortex never enters sys.modules.
    # Subprocess isolation keeps this honest when the cortex suite runs in the same session.
    from tests.helpers import cortex_modules_after
    setup = (
        "from contracts import Transform\n"
        "from conscience.agent_loop import ScriptedProposer, run_episode\n"
        "from conscience.cortex_client import FakeCortex\n"
        "scene = {'selector': 'tag:plumb', 'object': 'bronze_figure_03', "
        "'initial': Transform(pos=[0.0, 0.0, 0.40], quat=[0, 0, 0, 1])}\n"
        "run_episode(FakeCortex(), scene, proposer=ScriptedProposer())\n"
    )
    assert cortex_modules_after(setup) == [], \
        "the driver must never pull in cortex internals — only contracts + fixtures"


def test_loop_works_with_a_custom_client_via_the_protocol():
    """A different CortexClient (here a green-on-first-try stub) drives the same loop."""

    class AlwaysGreen:
        def __init__(self):
            self.committed: list[Diff] = []

        def sync_scene(self, selector: str) -> list[str]:
            return ["bronze_figure_03"]

        def validate_operation(self, diff: Diff) -> Verdict:
            return fixtures.VERDICT_REPAIRED

        def suggest_transform(self, obj: str, intent: dict) -> Transform:
            return fixtures.SUGGESTED_FIX

        def commit(self, diff: Diff) -> bool:
            self.committed.append(diff)
            return True

    client = AlwaysGreen()
    assert isinstance(client, CortexClient)
    steps = run_episode(client, _SCENE, proposer=ScriptedProposer())
    # First proposal already green -> a single step, committed immediately.
    assert len(steps) == 1
    assert steps[0].verdict.ok is True
    assert steps[0].committed is True
    assert len(client.committed) == 1
