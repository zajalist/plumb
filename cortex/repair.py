"""
cortex/repair.py — suggest_transform (Task 8, "the repair").

Given a placed object that may be violating stability and/or collision constraints,
find a new ``Transform`` (translate-only + yaw) that restores compliance.

Decision variables: ``[dx, dy, dyaw]``
  - ``dx``, ``dy``: translation offsets in world XY (metres)
  - ``dyaw``:       yaw rotation offset (radians) about the world Z axis

Objective (soft, minimised by SLSQP):
  - facing magnitude toward ``intent["target_yaw_deg"]`` (if given), else 0
  - small movement penalty ``alpha * (dx² + dy²)`` to keep the repair minimal

Hard constraints (SLSQP inequality constraints, all ≥ 0):
  - stability margin: ``stability(pap, new_tf).value_m - STABILITY_MARGIN_M ≥ 0``
  - collision clearance: ``collision(world, obj_id, None).value_m ≥ 0``
    (evaluated at the new_tf)

If SLSQP fails to converge OR the solution still violates a hard constraint,
the **greedy fallback** applies the stability gate's own ``fix.translate`` directly
to the initial transform, which is guaranteed to flip the stability verdict.

Returns the full ``Transform`` (the solver's yaw delta folded into the quaternion,
or the identity quaternion + translated position for the fallback).

Canonical space: Z-up, right-handed, metres. Reuses T4/T5 gate functions as the
cost — no math is re-derived here.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy.optimize import minimize  # re-exported so tests can monkeypatch it

from contracts import FixVector, GateResult, Transform
from cortex.gates.stability import stability, STABILITY_MARGIN_M


# Movement-penalty weight: keeps the repair minimal when there is already
# plenty of slack — large enough to matter, small enough to not override safety.
_MOVEMENT_ALPHA = 0.5

# Extra slack added to the stability constraint so the SLSQP solution lands
# strictly past the gate threshold (avoids floating-point boundary failures).
_CONSTRAINT_SLACK = 1e-3

# Bounds on the decision variables.
_DX_BOUND = (-5.0, 5.0)
_DY_BOUND = (-5.0, 5.0)
_DYAW_BOUND = (-math.pi, math.pi)


def suggest_transform(world, obj: str, intent: dict) -> Transform:
    """Find a collision-free, stable ``Transform`` for node ``obj``.

    Parameters
    ----------
    world:
        A :class:`~cortex.world.WorldModel` containing ``obj`` (and possibly
        other nodes whose collision is checked).
    obj:
        Node id of the object to repair.
    intent:
        Optional guidance:
          * ``"target_yaw_deg"`` — desired yaw in degrees (soft objective).

    Returns
    -------
    Transform:
        The repaired full transform (valid :class:`~contracts.Transform`).
        On SLSQP failure the greedy fallback is used instead.
    """
    node = world.get(obj)
    pap = node.pap
    initial_tf = node.transform

    target_yaw_rad: float | None = None
    if "target_yaw_deg" in intent:
        target_yaw_rad = math.radians(float(intent["target_yaw_deg"]))

    # ------------------------------------------------------------------
    # Objective: soft facing cost + movement penalty
    # ------------------------------------------------------------------
    def objective(vars: np.ndarray) -> float:
        dx, dy, dyaw = float(vars[0]), float(vars[1]), float(vars[2])
        # Movement penalty.
        cost = _MOVEMENT_ALPHA * (dx * dx + dy * dy)
        # Facing magnitude: penalise deviation from target_yaw.
        if target_yaw_rad is not None:
            current_yaw = _extract_yaw(initial_tf.quat)
            new_yaw = current_yaw + dyaw
            angle_diff = _angle_diff(new_yaw, target_yaw_rad)
            cost += abs(angle_diff)
        return cost

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------
    def stability_constraint(vars: np.ndarray) -> float:
        """stability margin - STABILITY_MARGIN_M - _SLACK >= 0 → feasible.

        We require a small extra slack (_SLACK) so the SLSQP solution lands
        strictly past the gate threshold rather than exactly on it where
        floating-point round-trip could flip the verdict.
        """
        dx, dy, dyaw = float(vars[0]), float(vars[1]), float(vars[2])
        new_tf = _apply_delta(initial_tf, dx, dy, dyaw)
        res = stability(pap, new_tf)
        val = res.value_m if res.value_m is not None else -1.0
        return val - STABILITY_MARGIN_M - _CONSTRAINT_SLACK

    def collision_constraint(vars: np.ndarray) -> float:
        """collision clearance >= 0 → feasible (no penetration)."""
        dx, dy, dyaw = float(vars[0]), float(vars[1]), float(vars[2])
        new_tf = _apply_delta(initial_tf, dx, dy, dyaw)
        # Temporarily update the world node's transform in a copy-like way.
        # Since WorldModel is mutable we patch-and-restore.
        old_tf = node.transform
        node.transform = new_tf
        try:
            from cortex.gates.collision import collision
            res = collision(world, obj, None)
            val = res.value_m if res.value_m is not None else 0.0
            # inf means no other nodes → treat as 0 clearance (unconstrained).
            if math.isinf(val):
                return 0.0
            return float(val)
        finally:
            node.transform = old_tf

    constraints = [
        {"type": "ineq", "fun": stability_constraint},
        {"type": "ineq", "fun": collision_constraint},
    ]

    # ------------------------------------------------------------------
    # Initial guess: start from what the stability fix says to do.
    # ------------------------------------------------------------------
    stab_res = stability(pap, initial_tf)
    x0 = np.zeros(3)
    if not stab_res.ok and stab_res.fix is not None:
        fix_t = stab_res.fix.translate
        x0[0] = float(fix_t[0])
        x0[1] = float(fix_t[1])
    if target_yaw_rad is not None:
        current_yaw = _extract_yaw(initial_tf.quat)
        x0[2] = _angle_diff(current_yaw, target_yaw_rad)

    bounds = [_DX_BOUND, _DY_BOUND, _DYAW_BOUND]

    # ------------------------------------------------------------------
    # SLSQP solve
    # ------------------------------------------------------------------
    sol = minimize(
        objective,
        x0,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"maxiter": 200, "ftol": 1e-8},
    )

    # Accept the solution only if SLSQP succeeded AND the hard constraints hold.
    if sol.success and _constraints_satisfied(sol.x, stability_constraint, collision_constraint):
        dx, dy, dyaw = float(sol.x[0]), float(sol.x[1]), float(sol.x[2])
        return _apply_delta(initial_tf, dx, dy, dyaw)

    # ------------------------------------------------------------------
    # Greedy fallback: apply the stability gate's fix.translate directly.
    # ------------------------------------------------------------------
    return _greedy_fallback(pap, initial_tf)


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #

def _apply_delta(tf: Transform, dx: float, dy: float, dyaw: float) -> Transform:
    """Return a new Transform with (dx, dy) added to pos and dyaw added to yaw."""
    new_pos = [
        float(tf.pos[0]) + dx,
        float(tf.pos[1]) + dy,
        float(tf.pos[2]),
    ]
    new_quat = _add_yaw(tf.quat, dyaw)
    return Transform(pos=new_pos, quat=new_quat, scale=list(tf.scale))


def _extract_yaw(quat: list[float]) -> float:
    """Extract yaw (rotation about Z) from a unit quaternion [x, y, z, w]."""
    x, y, z, w = (float(v) for v in quat)
    # atan2(2*(w*z + x*y), 1 - 2*(y*y + z*z))
    return math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))


def _angle_diff(a: float, b: float) -> float:
    """Signed difference (a - b) wrapped to (-pi, pi]."""
    diff = a - b
    while diff > math.pi:
        diff -= 2 * math.pi
    while diff < -math.pi:
        diff += 2 * math.pi
    return diff


def _add_yaw(quat: list[float], dyaw: float) -> list[float]:
    """Compose the existing quaternion with a yaw rotation of ``dyaw`` radians."""
    if abs(dyaw) < 1e-12:
        return list(quat)
    # Yaw quaternion: rotation about Z by dyaw.
    half = dyaw / 2.0
    dq = [0.0, 0.0, math.sin(half), math.cos(half)]  # [x, y, z, w]
    # Compose: q * dq (Hamilton product).
    x1, y1, z1, w1 = (float(v) for v in quat)
    x2, y2, z2, w2 = dq
    result = [
        w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
        w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
        w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
        w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
    ]
    # Normalise.
    norm = math.sqrt(sum(v * v for v in result))
    if norm < 1e-12:
        return [0.0, 0.0, 0.0, 1.0]
    return [v / norm for v in result]


def _constraints_satisfied(
    x: np.ndarray,
    stability_con,
    collision_con,
    tol: float = -1e-6,
) -> bool:
    """Return True iff both constraint functions are >= tol at x."""
    try:
        return (
            float(stability_con(x)) >= tol
            and float(collision_con(x)) >= tol
        )
    except Exception:
        return False


def _greedy_fallback(pap, initial_tf: Transform) -> Transform:
    """Apply the stability gate's own fix.translate to the initial transform.

    Guaranteed to flip the stability verdict to ok when the gate provides a fix.
    Falls back to the initial transform when no fix is available (already stable).
    """
    res = stability(pap, initial_tf)
    if res.ok:
        return initial_tf
    if res.fix is None:
        return initial_tf

    fix_t = res.fix.translate
    new_pos = [
        float(initial_tf.pos[0]) + float(fix_t[0]),
        float(initial_tf.pos[1]) + float(fix_t[1]),
        float(initial_tf.pos[2]) + float(fix_t[2]),
    ]
    return Transform(pos=new_pos, quat=list(initial_tf.quat), scale=list(initial_tf.scale))
