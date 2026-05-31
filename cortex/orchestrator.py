"""
cortex/orchestrator.py — validate_operation (Task 9).

``validate_operation(world, diff, laws=None) -> Verdict``:
  1. Apply the diff to a *copy* of the world (the original is never mutated).
  2. Run gates left → right: collision → stability → constraints → reach.
  3. Stop (halt) at the first **hard** failure; remaining gates are marked
     ``skipped=True`` and carry ``ok=None``.
  4. Populate ``stopped_at`` (the first hard-fail gate name, or ``None`` if all
     pass), each ``GateResult`` in ``gates``, and ``soft_cost`` (accumulated
     soft-constraint violation from the constraints gate).
  5. ``ok = no hard failure``.

Gate semantics
--------------
* **collision** — always hard: ``GateResult.ok`` is hard (we never allow objects
  to interpenetrate).
* **stability** — always hard: an unstable placement is never ok.
* **constraints** — mixed: the gate itself is hard if any *hard* law fails; soft
  violations are summed into ``soft_cost`` but do not stop the run.
* **reach** — always hard: a blocked walkway is never ok.

The ``laws`` parameter is forwarded to ``evaluate_constraints``; if ``None`` an
empty law list is used (the constraints gate trivially passes).

Canonical space everywhere: Z-up, right-handed, metres, kilograms.
"""

from __future__ import annotations

import copy
from typing import Optional

from contracts import (
    SCHEMA_VERSION,
    Diff,
    GateName,
    GateResult,
    Verdict,
)
from cortex.gates.collision import collision as _collision_gate
from cortex.gates.stability import stability as _stability_gate
from cortex.gates.constraints import evaluate_constraints as _constraints_gate
from cortex.gates.reach import reach as _reach_gate
from cortex.world import WorldModel


# Default walkway: a very large open area so the reach gate trivially passes when
# no walkway_poly is specified in the laws. Callers that care about reach should
# pass a ``walkway`` law via ``laws``.
_DEFAULT_WALKWAY: list[list[float]] = [
    [-1000.0, -1000.0],
    [ 1000.0, -1000.0],
    [ 1000.0,  1000.0],
    [-1000.0,  1000.0],
]


def validate_operation(
    world: WorldModel,
    diff: Diff,
    laws: Optional[list[dict]] = None,
) -> Verdict:
    """Apply ``diff`` to a copy of ``world`` and evaluate the gate stack.

    Parameters
    ----------
    world:
        The current :class:`~cortex.world.WorldModel`. Never mutated.
    diff:
        A :class:`~contracts.Diff` proposing a new transform for one node.
    laws:
        Optional list of constraint law specs forwarded to
        :func:`~cortex.gates.constraints.evaluate_constraints`.  If ``None``,
        an empty list is used (constraints gate trivially passes).

    Returns
    -------
    Verdict:
        Full gate stack result.  ``ok`` is ``True`` iff no hard gate failed.
    """
    laws = laws or []
    # A ``{"law": "free_standing"}`` marks the scene as objects resting on a ground plane
    # (e.g. forest trees on terrain): their support base co-moves with them, so stability
    # only fails on tilt/slope, not on lateral position. Absent → the pedestal model. It's
    # a scene-mode flag, not a constraint, so it's filtered out before the constraints gate.
    free_standing = any(spec.get("law") == "free_standing" for spec in laws)
    constraint_laws = [spec for spec in laws if spec.get("law") != "free_standing"]

    # --- 1. Apply diff to a deep copy ----------------------------------------
    staged = _apply_diff(world, diff)

    obj_id = diff.object

    # --- 2. Run gate stack ----------------------------------------------------
    gate_results: list[GateResult] = []
    stopped_at: Optional[GateName] = None
    soft_cost: float = 0.0
    halt = False  # set True after the first hard failure

    # --- Gate 1: collision ---------------------------------------------------
    if halt:
        gate_results.append(GateResult(gate=GateName.collision, skipped=True))
    else:
        col_result = _collision_gate(staged, obj_id, None)
        gate_results.append(col_result)
        if not col_result.ok:
            stopped_at = GateName.collision
            halt = True

    # --- Gate 2: stability ---------------------------------------------------
    if halt:
        gate_results.append(GateResult(gate=GateName.stability, skipped=True))
    else:
        node = staged.get(obj_id)
        stab_result = _stability_gate(node.pap, node.transform, anchored=not free_standing)
        gate_results.append(stab_result)
        if not stab_result.ok:
            stopped_at = GateName.stability
            halt = True

    # --- Gate 3: constraints -------------------------------------------------
    if halt:
        gate_results.append(GateResult(gate=GateName.constraints, skipped=True))
    else:
        con_result = _constraints_gate(staged, constraint_laws)
        gate_results.append(con_result)
        # Soft violations: accumulate into soft_cost but do NOT halt.
        soft_cost += float(con_result.value_m or 0.0)
        if not con_result.ok:
            # A hard law failed inside constraints → halt.
            stopped_at = GateName.constraints
            halt = True

    # --- Gate 4: reach -------------------------------------------------------
    if halt:
        gate_results.append(GateResult(gate=GateName.reach, skipped=True))
    else:
        # Extract walkway from laws if a "walkway" law is present; else use default.
        walkway_poly = _extract_walkway_poly(laws)
        rch_result = _reach_gate(staged, walkway_poly)
        gate_results.append(rch_result)
        if not rch_result.ok:
            stopped_at = GateName.reach
            halt = True

    ok = stopped_at is None

    return Verdict(
        schema_version=SCHEMA_VERSION,
        ok=ok,
        stopped_at=stopped_at,
        gates=gate_results,
        soft_cost=soft_cost,
    )


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #

def _apply_diff(world: WorldModel, diff: Diff) -> WorldModel:
    """Return a new WorldModel with ``diff`` applied. The original is NOT mutated."""
    staged = WorldModel()
    for nid in world.nodes():
        node = world.get(nid)
        tf = diff.transform if nid == diff.object else node.transform
        staged.add(nid, node.pap, tf, parent=node.parent)
    return staged


def _extract_walkway_poly(laws: list[dict]) -> list[list[float]]:
    """Return the first walkway polygon found in ``laws``, or the default open space."""
    for spec in laws:
        if spec.get("law") == "walkway":
            poly = spec.get("walkway_poly")
            if poly:
                return list(poly)
    return _DEFAULT_WALKWAY
