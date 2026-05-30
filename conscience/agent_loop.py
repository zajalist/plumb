"""
The agent loop (Task B4) — the driver that turns a verdict into a corrected placement.

`run_episode(client, scene)` plays the demo beat against any `CortexClient`:

    sync  ->  propose a diff  ->  validate_operation
          ->  if it fails: read structured diagnostics (which gate, what number,
              which way)  ->  suggest_transform  ->  re-validate
          ->  commit (only once green)

It returns a scrubbable list of `Step`s — one (proposal, verdict) pair per attempt —
so the timeline can scrub topple → repair. The "agent" is swappable behind the
`Proposer` interface: a `ScriptedProposer` (the canned topple→repair sequence) drives
it today; a real-LLM proposer drops in behind the same interface later, unchanged.

Never a bare "no": when a verdict fails, `read_diagnostics` pulls the failing gate,
its signed magnitude, and its fix vector straight out of the Verdict JSON — that is
the structured "which way back to safe" the loop acts on.

Pure consumer of the contract: no physics, and `cortex/` is never imported.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol

from contracts import Diff, FixVector, GateName, GateResult, Transform, Verdict
from conscience.cortex_client import CortexClient

# A hard cap so a misbehaving cortex/proposer can never spin the loop forever. The
# demo beat needs exactly two attempts (topple, then repair); a couple of spare
# rounds is plenty of head-room without risking an infinite loop.
_MAX_ATTEMPTS = 8


# --------------------------------------------------------------------------- #
# Structured diagnostics — the "which gate, what number, which way" off a Verdict.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Diagnostic:
    """
    The actionable read of a failing verdict: the gate that stopped the commit, its
    signed headline number, the fix vector to apply, and any viz/detail hints. This
    is what makes the loop "never a bare no" — it always knows which way to move.
    """

    gate: GateName
    value_m: Optional[float]
    fix: Optional[FixVector]
    viz: Optional[str] = None
    detail: Optional[str] = None


def _failing_gate(verdict: Verdict) -> Optional[GateResult]:
    """The gate that stopped the commit: the `stopped_at` gate, else the first hard fail."""
    if verdict.stopped_at is not None:
        for g in verdict.gates:
            if g.gate == verdict.stopped_at:
                return g
    for g in verdict.gates:
        if g.ok is False and not g.skipped:
            return g
    return None


def read_diagnostics(verdict: Verdict) -> Optional[Diagnostic]:
    """
    Read structured diagnostics off a Verdict — or `None` when it is green.

    On `VERDICT_TOPPLE` this returns the stability gate, its signed margin
    (`-0.07` m — CoM 7cm outside the polygon) and the fix vector
    (`[0.06, 0, 0]` — the way back to safe). The loop feeds that into the cortex's
    `suggest_transform` as the repair objective.
    """
    if verdict.ok:
        return None
    g = _failing_gate(verdict)
    if g is None:
        return None
    return Diagnostic(
        gate=g.gate,
        value_m=g.value_m,
        fix=g.fix,
        viz=g.viz,
        detail=g.detail,
    )


# --------------------------------------------------------------------------- #
# A scrubbable step: one (proposal, verdict) pair on the timeline.
# --------------------------------------------------------------------------- #
@dataclass
class Step:
    """
    One attempt on the timeline: the diff the agent proposed, the verdict it got
    back, and whether this attempt was the one that got committed. The diagnostics
    (when the verdict failed) ride along so the UI can render *why* without re-reading.
    """

    proposal: Diff
    verdict: Verdict
    committed: bool = False
    diagnostic: Optional[Diagnostic] = None


# --------------------------------------------------------------------------- #
# The proposer seam — the swappable "agent".
# --------------------------------------------------------------------------- #
class Proposer(Protocol):
    """
    The agent as the loop sees it: it makes the FIRST proposal from the scene. Repairs
    after a failed verdict come from the cortex's `suggest_transform`, so the proposer
    only needs to kick off the episode. A `ScriptedProposer` does the canned thing;
    a real LLM proposer is the same shape.
    """

    def initial(self, scene: dict) -> Diff:
        """The opening move: the object and transform to try first."""


@dataclass
class ScriptedProposer:
    """
    The canned driver — places the object "by vibes" exactly where the scene says,
    which (in the demo) is too close to the edge and topples. The repair is not the
    proposer's job; the loop asks the cortex for `suggest_transform` and re-validates.

    Defaults reproduce the Gallery beat: `bronze_figure_03` at the toppling spot.
    """

    object: str = "bronze_figure_03"
    transform: Transform = field(
        default_factory=lambda: Transform(pos=[0.0, 0.0, 0.40], quat=[0, 0, 0, 1])
    )

    def initial(self, scene: dict) -> Diff:
        obj = scene.get("object", self.object)
        t = scene.get("initial", self.transform)
        return Diff(object=obj, transform=t)


# --------------------------------------------------------------------------- #
# The loop.
# --------------------------------------------------------------------------- #
def run_episode(
    client: CortexClient,
    scene: dict,
    *,
    proposer: Optional[Proposer] = None,
) -> list[Step]:
    """
    Drive one episode to a green verdict and return the scrubbable step list.

    Sequence:
      1. `sync_scene` so the cortex and the loop agree on the world.
      2. The proposer makes the opening diff; `validate_operation` judges it.
      3. While the verdict fails: `read_diagnostics` -> `suggest_transform` (toward the
         fix) -> propose the suggested transform -> `validate_operation` again.
      4. On the first green verdict: `commit` (exactly once, never before green) and
         mark that step committed.

    Each attempt is recorded as a `Step` (proposal + verdict [+ diagnostic]). The loop
    is a PURE consumer of the contract — it computes no physics and never imports cortex.
    """
    if proposer is None:
        proposer = ScriptedProposer()

    # 1. Agree on the world. (We don't need the ids for the scripted beat, but the
    #    real loop syncs first and so must this one — it's part of the contract dance.)
    client.sync_scene(scene.get("selector", "tag:plumb"))

    steps: list[Step] = []

    # 2. Opening proposal.
    proposal = proposer.initial(scene)

    for _ in range(_MAX_ATTEMPTS):
        verdict = client.validate_operation(proposal)

        if verdict.ok:
            # First green verdict -> commit, exactly once, only now.
            client.commit(proposal)
            steps.append(Step(proposal=proposal, verdict=verdict, committed=True))
            return steps

        # Failed: record why, then ask the cortex which way back to safe.
        diag = read_diagnostics(verdict)
        steps.append(Step(proposal=proposal, verdict=verdict,
                          committed=False, diagnostic=diag))

        intent = _repair_intent(proposal.object, diag)
        fixed = client.suggest_transform(proposal.object, intent)
        proposal = Diff(object=proposal.object, transform=fixed)

    # Ran out of attempts without going green. Hand back what we have rather than
    # raise: the caller (and the timeline) still gets the full scrub trail, and the
    # commit-once discipline guarantees nothing un-green was ever committed.
    return steps


def _repair_intent(obj: str, diag: Optional[Diagnostic]) -> dict:
    """Turn a diagnostic into the `intent` dict handed to `suggest_transform`."""
    intent: dict = {"object": obj, "goal": "satisfy_gates"}
    if diag is not None:
        intent["gate"] = diag.gate.value
        if diag.value_m is not None:
            intent["value_m"] = diag.value_m
        if diag.fix is not None:
            intent["fix_translate"] = list(diag.fix.translate)
            if diag.fix.rotate_quat is not None:
                intent["fix_rotate_quat"] = list(diag.fix.rotate_quat)
    return intent
