"""
cortex/gates/constraints.py — hardcoded laws registry (Task 7).

A registry of law cost functions, each ``(world, params) -> ConstraintResult``
(name, ok, hard, magnitude, detail). Implemented laws:

  * **facing**       — soft: angle between an object's ``front`` and the direction
                       to a target ≤ tol; magnitude = degrees over tolerance.
  * **com_over_base**— hard: wraps :func:`~cortex.gates.stability.stability`,
                       exposes the margin violation as magnitude.
  * **walkway**      — hard: wraps :func:`~cortex.gates.reach.reach`, exposes
                       the width shortfall as magnitude.
  * **door_clear**   — hard: collision between a node and a swept-volume obstacle
                       node via :func:`~cortex.gates.collision.collision`.

``evaluate_constraints(world, laws) -> GateResult`` aggregates a list of law
specs (each a dict with a ``"law"`` key + law-specific params); the gate is
``ok`` iff all *hard* laws pass; soft magnitudes are summed into ``value_m``.

Canonical space: Z-up, right-handed, metres, kilograms.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from contracts import ConstraintResult, GateName, GateResult

# ──────────────────────────────────────────────────────────────────────────────
# Law registry
# ──────────────────────────────────────────────────────────────────────────────

_LAW_REGISTRY: dict[str, Any] = {}


def _register(name: str):
    """Decorator that registers a law function under ``name``."""
    def decorator(fn):
        _LAW_REGISTRY[name] = fn
        return fn
    return decorator


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def evaluate_constraints(world, laws: list[dict]) -> GateResult:
    """Aggregate a list of law specs into a single GateResult for the constraints gate.

    Parameters
    ----------
    world:
        A :class:`~cortex.world.WorldModel`.
    laws:
        List of dicts, each with a ``"law"`` key naming a registered law plus
        law-specific parameters (e.g. ``{"law": "facing", "node": "chair",
        "target": [1,2,0], "tol_deg": 15}``).

    Returns
    -------
    GateResult:
      * ``gate = GateName.constraints``
      * ``ok = True`` iff all hard laws pass (soft failures do not gate)
      * ``constraints`` = per-law :class:`~contracts.ConstraintResult` list
      * ``value_m`` = sum of soft-law violation magnitudes (the ``soft_cost``)
    """
    results: list[ConstraintResult] = []
    for spec in laws:
        spec = dict(spec)  # don't mutate caller's dict
        law_name = spec.pop("law")
        fn = _LAW_REGISTRY.get(law_name)
        if fn is None:
            raise ValueError(f"Unknown constraint law: {law_name!r}")
        cr = fn(world, spec)
        results.append(cr)

    gate_ok = all(cr.ok for cr in results if cr.hard)
    soft_cost = sum(cr.magnitude for cr in results if not cr.hard and not cr.ok)

    return GateResult(
        gate=GateName.constraints,
        ok=gate_ok,
        value_m=soft_cost,
        constraints=results,
    )


# ──────────────────────────────────────────────────────────────────────────────
# facing law (soft)
# ──────────────────────────────────────────────────────────────────────────────

@_register("facing")
def facing(world, params: dict) -> ConstraintResult:
    """Soft law: angle between ``front`` and direction-to-target ≤ tol.

    Parameters (in ``params``)
    --------------------------
    node : str
        The world node whose ``pap.semantics.front`` is used.
    target : list[float]
        World-space [x, y, z] the object should face.
    tol_deg : float
        Tolerance in degrees (default 15).

    Returns
    -------
    ConstraintResult:
      * ``hard = False`` (soft law)
      * ``ok = True`` if angle ≤ tol
      * ``magnitude`` = degrees over tolerance (0 when satisfied)
      * ``detail`` like ``"Δ23°"`` or ``"Δ0°"``
    """
    node_id = params["node"]
    target = np.asarray(params["target"], dtype=float)
    tol_deg = float(params.get("tol_deg", 15.0))

    node = world.get(node_id)
    pap = node.pap
    tf = node.transform

    # Resolve the object's world-space front direction.
    front_local = np.asarray(pap.semantics.front, dtype=float)
    front_world = _rotate_vector(front_local, tf.quat)

    # Direction from the object's position to the target.
    pos = np.asarray(tf.pos, dtype=float)
    to_target = target - pos
    dist = float(np.linalg.norm(to_target))
    if dist < 1e-9:
        # Target == object position: trivially ok.
        return ConstraintResult(
            name="facing",
            ok=True,
            hard=False,
            magnitude=0.0,
            detail="Δ0°",
        )

    to_target_unit = to_target / dist
    front_norm = float(np.linalg.norm(front_world))
    if front_norm < 1e-9:
        front_world = np.array([0.0, 1.0, 0.0])
    else:
        front_world = front_world / front_norm

    # Angle between front and to_target (clamp for numerical safety).
    dot = float(np.clip(np.dot(front_world, to_target_unit), -1.0, 1.0))
    angle_deg = math.degrees(math.acos(dot))

    over = max(0.0, angle_deg - tol_deg)
    ok = over < 1e-9

    detail = f"Δ{int(round(over))}°"

    return ConstraintResult(
        name="facing",
        ok=ok,
        hard=False,
        magnitude=float(round(over, 4)),
        detail=detail,
    )


# ──────────────────────────────────────────────────────────────────────────────
# min_spacing law (soft by default) — forest comfort spacing
# ──────────────────────────────────────────────────────────────────────────────

@_register("min_spacing")
def min_spacing(world, params: dict) -> ConstraintResult:
    """Every pair of placed nodes is at least ``distance_m`` apart in the ground plane
    (origin-to-origin XY — trunk-to-trunk for trees). The collision gate already forbids
    overlap; this adds a comfort margin so a forest isn't jammed together.

    Parameters (in ``params``)
    --------------------------
    distance_m : float
        Required separation in metres (default 1.0).
    hard : bool
        If true the law gates (a too-close pair fails the scene); default soft (it only
        accumulates ``magnitude`` into the soft cost).

    Returns
    -------
    ConstraintResult: ``magnitude`` = the largest shortfall across all pairs (0 if clear).
    """
    distance = float(params.get("distance_m", 1.0))
    hard = bool(params.get("hard", False))
    ids = world.nodes()
    worst = 0.0
    closest: tuple[str, str, float] | None = None
    for i in range(len(ids)):
        a = world.get(ids[i]).transform.pos
        for j in range(i + 1, len(ids)):
            b = world.get(ids[j]).transform.pos
            d = math.hypot(float(a[0]) - float(b[0]), float(a[1]) - float(b[1]))
            short = distance - d
            if short > worst:
                worst, closest = short, (ids[i], ids[j], d)
    ok = worst < 1e-9
    detail = (f"{closest[0]}↔{closest[1]} {closest[2] * 100:.0f}cm (< {distance * 100:.0f}cm)"
              if closest else "spacing ok")
    return ConstraintResult(name="min_spacing", ok=ok, hard=hard,
                            magnitude=float(round(max(0.0, worst), 4)), detail=detail)


# ──────────────────────────────────────────────────────────────────────────────
# com_over_base law (hard)
# ──────────────────────────────────────────────────────────────────────────────

@_register("com_over_base")
def com_over_base(world, params: dict) -> ConstraintResult:
    """Hard law: wraps the stability gate margin.

    Parameters (in ``params``)
    --------------------------
    node : str
        The world node to check.

    Returns
    -------
    ConstraintResult:
      * ``hard = True``
      * ``ok = True`` if the stability margin ≥ STABILITY_MARGIN_M
      * ``magnitude`` = |violation| in metres (0 when ok)
      * ``detail`` proxied from the stability gate
    """
    from cortex.gates.stability import stability, STABILITY_MARGIN_M

    node_id = params["node"]
    node = world.get(node_id)
    gate = stability(node.pap, node.transform)

    ok = bool(gate.ok)
    if ok:
        magnitude = 0.0
    else:
        # margin is negative → violation = STABILITY_MARGIN_M - margin
        margin = gate.value_m if gate.value_m is not None else 0.0
        magnitude = float(abs(STABILITY_MARGIN_M - margin))

    return ConstraintResult(
        name="com_over_base",
        ok=ok,
        hard=True,
        magnitude=magnitude,
        detail=gate.detail,
    )


# ──────────────────────────────────────────────────────────────────────────────
# walkway law (hard)
# ──────────────────────────────────────────────────────────────────────────────

@_register("walkway")
def walkway(world, params: dict) -> ConstraintResult:
    """Hard law: wraps the reach gate.

    Parameters (in ``params``)
    --------------------------
    walkway_poly : list[list[float]]
        2-D walkway polygon vertices [[x, y], ...].
    agent_r : float
        Agent radius in metres (default 0.45).
    start : list[float] | None
        Optional flood-fill start point [x, y].
    goal : list[float] | None
        Optional flood-fill goal point [x, y].

    Returns
    -------
    ConstraintResult:
      * ``hard = True``
      * ``ok`` proxied from the reach gate
      * ``magnitude`` = shortfall in metres (0 when ok)
      * ``detail`` proxied from the reach gate
    """
    from cortex.gates.reach import reach

    walkway_poly = params["walkway_poly"]
    agent_r = float(params.get("agent_r", 0.45))
    start = params.get("start")
    goal = params.get("goal")

    gate = reach(world, walkway_poly, agent_r=agent_r, start=start, goal=goal)

    diameter = 2.0 * agent_r
    ok = bool(gate.ok)
    if ok:
        magnitude = 0.0
    else:
        width = gate.value_m if gate.value_m is not None else 0.0
        magnitude = float(max(0.0, diameter - width))

    return ConstraintResult(
        name="walkway",
        ok=ok,
        hard=True,
        magnitude=magnitude,
        detail=gate.detail,
    )


# ──────────────────────────────────────────────────────────────────────────────
# door_clear law (hard)
# ──────────────────────────────────────────────────────────────────────────────

@_register("door_clear")
def door_clear(world, params: dict) -> ConstraintResult:
    """Hard law: collision between ``node`` and the swept-volume ``sweep_node``.

    The swept-volume obstacle is a pre-computed node in the world (e.g. the union
    of all door-hull poses rotated through the hinge range, stored as a static
    convex mesh node). This law is simply a collision check between the two nodes.

    Parameters (in ``params``)
    --------------------------
    node : str
        The world node that must not intersect the sweep.
    sweep_node : str
        The world node representing the swept volume (the door arc obstacle).

    Returns
    -------
    ConstraintResult:
      * ``hard = True``
      * ``ok = True`` if clearance ≥ 0 (no penetration)
      * ``magnitude`` = penetration depth in metres (0 when ok)
      * ``detail`` proxied from the collision gate
    """
    from cortex.gates.collision import collision

    node_id = params["node"]
    sweep_id = params["sweep_node"]

    gate = collision(world, node_id, sweep_id)

    ok = bool(gate.ok)
    if ok:
        magnitude = 0.0
    else:
        val = gate.value_m if gate.value_m is not None else 0.0
        magnitude = float(abs(val))  # penetration depth (positive number)

    return ConstraintResult(
        name="door_clear",
        ok=ok,
        hard=True,
        magnitude=magnitude,
        detail=gate.detail,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────────────────────

def _rotate_vector(vec: np.ndarray, quat: list[float]) -> np.ndarray:
    """Rotate a 3-vector by a unit quaternion [x, y, z, w]."""
    x, y, z, w = (float(v) for v in quat)
    n = math.sqrt(x * x + y * y + z * z + w * w)
    if n < 1e-9:
        return vec.copy()
    x, y, z, w = x / n, y / n, z / n, w / n
    rot = np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ],
        dtype=float,
    )
    return rot @ np.asarray(vec, dtype=float)
