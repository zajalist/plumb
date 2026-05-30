"""
The cortex client seam (Task B4) — `CortexClient` Protocol + a `FakeCortex`.

This is the swap point between the conscience and the cortex. The agent loop talks
ONLY to a `CortexClient`; today that is a fixtures-backed `FakeCortex`, and the day
Person A's MCP server lands a real `McpCortex` implements the same four methods and
drops straight in — the loop never changes a line.

The four methods mirror the MCP tool surface the loop relies on (see
`contracts.MCP_TOOLS`):

    sync_scene(selector)            -> list[node_id]
    validate_operation(diff)        -> Verdict
    suggest_transform(obj, intent)  -> Transform
    commit(diff)                    -> bool

`FakeCortex` plays the demo beat straight out of `fixtures.py`: a first proposal
topples (`VERDICT_TOPPLE`), and once the cortex's own `suggest_transform` nudge has
been applied the re-validation passes (`VERDICT_REPAIRED`). It is a PURE consumer of
the contract — it never imports anything from `cortex/`.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import fixtures
from contracts import Diff, Transform, Verdict


@runtime_checkable
class CortexClient(Protocol):
    """
    The cortex as the conscience sees it — the validate / suggest / commit surface.

    Anything that provides these four methods is a drop-in for the loop:
    `FakeCortex` today, a real MCP-backed `McpCortex` tomorrow. `runtime_checkable`
    so tests can assert `isinstance(client, CortexClient)` at the seam.
    """

    def sync_scene(self, selector: str) -> list[str]:
        """Return the node ids of the actors matching `selector` (e.g. "tag:plumb")."""

    def validate_operation(self, diff: Diff) -> Verdict:
        """Run the gate stack on a proposed `diff` and return the structured Verdict."""

    def suggest_transform(self, obj: str, intent: dict) -> Transform:
        """Return a transform that satisfies `intent` (e.g. nudge an object back to stable)."""

    def commit(self, diff: Diff) -> bool:
        """Persist a validated `diff`. The caller is responsible for only committing green."""


def _transforms_equal(a: Transform, b: Transform, *, tol: float = 1e-9) -> bool:
    """Component-wise equality of two transforms, within a tiny tolerance."""
    return (
        all(abs(x - y) <= tol for x, y in zip(a.pos, b.pos))
        and all(abs(x - y) <= tol for x, y in zip(a.quat, b.quat))
        and all(abs(x - y) <= tol for x, y in zip(a.scale, b.scale))
    )


class FakeCortex:
    """
    Fixtures-backed cortex stand-in — the whole topple→repair beat, no MCP needed.

    `validate_operation` is keyed off the *transform*, not call order, so it behaves
    correctly however the loop drives it: a proposal whose transform matches the
    cortex's suggested fix (`fixtures.SUGGESTED_FIX`) reads as repaired/green
    (`VERDICT_REPAIRED`); any other proposal reads as the topple (`VERDICT_TOPPLE`).
    That mirrors the spec — "after a suggest_transform-applied diff → VERDICT_REPAIRED".

    `commit` records committed diffs on `self.committed` so the loop's
    "never commit before green" discipline is observable in tests.
    """

    def __init__(self, objects: list[str] | None = None):
        self.objects: list[str] = list(objects) if objects is not None else ["bronze_figure_03"]
        self.committed: list[Diff] = []
        # Every verdict handed out, in order — a scrub trail for inspection.
        self.validations: list[Verdict] = []

    def sync_scene(self, selector: str) -> list[str]:
        """Return the (static, fixture-backed) set of objects in the scene."""
        return list(self.objects)

    def validate_operation(self, diff: Diff) -> Verdict:
        """Topple by default; pass once the suggested fix transform has been applied."""
        if _transforms_equal(diff.transform, fixtures.SUGGESTED_FIX):
            verdict = fixtures.VERDICT_REPAIRED
        else:
            verdict = fixtures.VERDICT_TOPPLE
        self.validations.append(verdict)
        return verdict

    def suggest_transform(self, obj: str, intent: dict) -> Transform:
        """Hand back the cortex's recovery nudge (the fixture fix)."""
        return fixtures.SUGGESTED_FIX

    def commit(self, diff: Diff) -> bool:
        """Record the committed diff. The loop only ever calls this on a green verdict."""
        self.committed.append(diff)
        return True
