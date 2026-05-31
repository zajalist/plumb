"""
cortex/server.py — FastMCP surface (Task 10).

Exposes every tool in ``contracts.MCP_TOOLS`` over FastMCP (stdio), delegating
to the cortex modules. The server maintains a shared :class:`~cortex.world.WorldModel`
that ``sync_scene`` / ``commit`` keep in sync with the UE5 world (stubs that
Person B's bridge fills).

Tool list (mirrors ``contracts.MCP_TOOLS``):
  * ``sync_scene``         — stub: Person B fills; returns current node ids
  * ``bake_asset``         — geometry + physical bake → PAP JSON
  * ``get_profile``        — retrieve a stored PAP by asset id (stub for now)
  * ``check_collision``    — collision gate on one or two nodes → GateResult JSON
  * ``simulate_drop``      — stability gate for a node → GateResult JSON
  * ``path_clear``         — reach gate → GateResult JSON
  * ``evaluate_constraints``— constraints gate → GateResult JSON
  * ``validate_operation`` — full gate stack → Verdict JSON
  * ``suggest_transform``  — repair → Transform JSON
  * ``commit``             — stub: Person B fills; applies a diff to the world

All tools accept / return JSON-serialisable dicts (Pydantic ``.model_dump()``).

Canonical space: Z-up, right-handed, metres, kilograms.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from fastmcp import FastMCP

from contracts import (
    Diff,
    GateName,
    GateResult,
    MCP_TOOLS,
    PAP,
    Transform,
    Verdict,
)
from cortex.bake import bake_asset as _bake_asset
from cortex.gates.collision import collision as _collision
from cortex.gates.constraints import evaluate_constraints as _evaluate_constraints
from cortex.gates.reach import reach as _reach
from cortex.gates.stability import stability as _stability
from cortex.orchestrator import validate_operation as _validate_operation
from cortex.repair import suggest_transform as _suggest_transform
from cortex.world import WorldModel

# --------------------------------------------------------------------------- #
# Shared world state
# --------------------------------------------------------------------------- #
# The server holds one WorldModel. ``sync_scene`` (and B's bridge) populate it;
# ``commit`` mutates it; all gate tools read it.
_world: WorldModel = WorldModel()

# PAP store: asset_id -> PAP (populated by bake_asset / sync_scene).
_pap_store: dict[str, PAP] = {}


# --------------------------------------------------------------------------- #
# FastMCP app
# --------------------------------------------------------------------------- #
mcp = FastMCP("plumb-cortex")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _world_from_dict(d: dict) -> WorldModel:
    """Reconstruct a WorldModel from a ``_world_to_dict`` serialised dict.

    Used so that test callers can pass self-contained world state without
    mutating the global ``_world``.  When ``world_json`` is ``None`` the global
    ``_world`` is used.
    """
    w = WorldModel()
    from contracts import PAP, Transform
    for nid, node_d in d.get("nodes", {}).items():
        pap = PAP.model_validate(node_d["pap"])
        tf = Transform.model_validate(node_d["transform"])
        w.add(nid, pap, tf, parent=node_d.get("parent"))
    return w


# --------------------------------------------------------------------------- #
# Tool: sync_scene
# --------------------------------------------------------------------------- #
@mcp.tool()
def sync_scene(selector: str = "*") -> str:
    """Stub: return node ids currently in the server world.

    Person B's UE5 bridge replaces this body to push world state to the server.
    The cortex side just reports what nodes it currently holds.

    Returns
    -------
    JSON array of node-id strings.
    """
    return json.dumps(_world.nodes())


# --------------------------------------------------------------------------- #
# Tool: bake_asset
# --------------------------------------------------------------------------- #
@mcp.tool()
def bake_asset(
    asset_id: str,
    mesh_path: str,
    part_materials_json: Optional[str] = None,
    profile: str = "rigid_prop",
) -> str:
    """Bake a PAP from a mesh file.

    Parameters
    ----------
    asset_id:
        Unique identifier for this asset (e.g. ``"bronze_figure_03"``).
    mesh_path:
        Absolute path to the mesh file (OBJ, GLB, STL, …).
    part_materials_json:
        Optional JSON string mapping part index/name → material name
        (e.g. ``'{"0": "bronze", "1": "stone"}'``).
    profile:
        Bake profile name (default ``"rigid_prop"``).

    Returns
    -------
    JSON-serialised :class:`~contracts.PAP`.
    """
    part_materials: dict | None = None
    if part_materials_json:
        part_materials = json.loads(part_materials_json)

    pap = _bake_asset(asset_id, mesh_path, part_materials, profile)
    _pap_store[asset_id] = pap
    return pap.model_dump_json()


# --------------------------------------------------------------------------- #
# Tool: get_profile
# --------------------------------------------------------------------------- #
@mcp.tool()
def get_profile(asset_id: str) -> str:
    """Return a previously baked PAP for an asset.

    Returns
    -------
    JSON-serialised :class:`~contracts.PAP`, or ``{}`` if unknown.
    """
    pap = _pap_store.get(asset_id)
    if pap is None:
        return json.dumps({})
    return pap.model_dump_json()


# --------------------------------------------------------------------------- #
# Tool: check_collision
# --------------------------------------------------------------------------- #
@mcp.tool()
def check_collision(
    a: str,
    b: Optional[str] = None,
    world_json: Optional[dict] = None,
) -> str:
    """Collision gate between node ``a`` and node ``b`` (or all nodes if ``b`` is None).

    Parameters
    ----------
    a:
        Node id to check.
    b:
        Optional second node id. ``None`` checks ``a`` against all other nodes.
    world_json:
        Optional serialised world dict (see ``_world_to_dict`` in tests).
        When ``None`` the server's global world is used.

    Returns
    -------
    JSON-serialised :class:`~contracts.GateResult`.
    """
    world = _world_from_dict(world_json) if world_json else _world
    result = _collision(world, a, b)
    return result.model_dump_json()


# --------------------------------------------------------------------------- #
# Tool: simulate_drop  (stability)
# --------------------------------------------------------------------------- #
@mcp.tool()
def simulate_drop(
    obj: str,
    t: float = 0.0,
    world_json: Optional[dict] = None,
) -> str:
    """Stability gate for node ``obj``.

    ``t`` is reserved for future time-step simulation; currently ignored.

    Returns
    -------
    JSON-serialised :class:`~contracts.GateResult`.
    """
    world = _world_from_dict(world_json) if world_json else _world
    node = world.get(obj)
    result = _stability(node.pap, node.transform)
    return result.model_dump_json()


# --------------------------------------------------------------------------- #
# Tool: path_clear  (reach)
# --------------------------------------------------------------------------- #
@mcp.tool()
def path_clear(
    walkway_poly_json: str,
    start: Optional[list[float]] = None,
    goal: Optional[list[float]] = None,
    r: float = 0.45,
    world_json: Optional[dict] = None,
) -> str:
    """Reach gate: narrowest free-passage width along the walkway polygon.

    Parameters
    ----------
    walkway_poly_json:
        JSON string of ``[[x, y], ...]`` polygon vertices defining the walkway.
    start:
        Optional [x, y] start point for flood-fill reachability.
    goal:
        Optional [x, y] goal point for flood-fill reachability.
    r:
        Agent radius in metres (default 0.45).
    world_json:
        Optional serialised world dict. When ``None`` the global world is used.

    Returns
    -------
    JSON-serialised :class:`~contracts.GateResult`.
    """
    world = _world_from_dict(world_json) if world_json else _world
    walkway_poly = json.loads(walkway_poly_json)
    result = _reach(world, walkway_poly, agent_r=r, start=start, goal=goal)
    return result.model_dump_json()


# --------------------------------------------------------------------------- #
# Tool: evaluate_constraints
# --------------------------------------------------------------------------- #
@mcp.tool()
def evaluate_constraints(
    laws_json: str = "[]",
    world_json: Optional[dict] = None,
) -> str:
    """Constraints gate: evaluate a list of law specs.

    Parameters
    ----------
    laws_json:
        JSON array of law-spec dicts, each with a ``"law"`` key, e.g.
        ``'[{"law":"facing","node":"chair","target":[1,2,0],"tol_deg":15}]'``.
    world_json:
        Optional serialised world dict. When ``None`` the global world is used.

    Returns
    -------
    JSON-serialised :class:`~contracts.GateResult`.
    """
    world = _world_from_dict(world_json) if world_json else _world
    laws: list[dict] = json.loads(laws_json)
    result = _evaluate_constraints(world, laws)
    return result.model_dump_json()


# --------------------------------------------------------------------------- #
# Tool: validate_operation
# --------------------------------------------------------------------------- #
@mcp.tool()
def validate_operation(
    diff_json: dict,
    world_json: Optional[dict] = None,
    laws_json: str = "[]",
) -> str:
    """Full gate stack → Verdict.

    Parameters
    ----------
    diff_json:
        Serialised :class:`~contracts.Diff` dict
        (``{"object": "node_id", "transform": {...}}``).
    world_json:
        Optional serialised world dict. When ``None`` the global world is used.
    laws_json:
        Optional JSON array of constraint law specs (forwarded to the
        constraints gate).

    Returns
    -------
    JSON-serialised :class:`~contracts.Verdict`.
    """
    world = _world_from_dict(world_json) if world_json else _world
    diff = Diff.model_validate(diff_json)
    laws: list[dict] = json.loads(laws_json)
    verdict = _validate_operation(world, diff, laws or None)
    return verdict.model_dump_json()


# --------------------------------------------------------------------------- #
# Tool: suggest_transform
# --------------------------------------------------------------------------- #
@mcp.tool()
def suggest_transform(
    obj: str,
    intent_json: str = "{}",
    world_json: Optional[dict] = None,
) -> str:
    """Repair: find a stable, collision-free transform for node ``obj``.

    Parameters
    ----------
    obj:
        Node id to repair.
    intent_json:
        Optional JSON dict with repair hints (e.g. ``'{"target_yaw_deg": 90}'``).
    world_json:
        Optional serialised world dict. When ``None`` the global world is used.

    Returns
    -------
    JSON-serialised :class:`~contracts.Transform`.
    """
    world = _world_from_dict(world_json) if world_json else _world
    intent: dict = json.loads(intent_json)
    tf = _suggest_transform(world, obj, intent)
    return tf.model_dump_json()


# --------------------------------------------------------------------------- #
# Tool: commit
# --------------------------------------------------------------------------- #
@mcp.tool()
def commit(diff_json: dict) -> str:
    """Stub: apply a diff to the server's world model.

    Person B's UE5 bridge replaces this body with the real commit.
    The cortex side applies the transform to the shared world and returns True.

    Returns
    -------
    JSON ``true`` / ``false``.
    """
    diff = Diff.model_validate(diff_json)
    try:
        _world.update_transform(diff.object, diff.transform)
        return json.dumps(True)
    except KeyError:
        # Node not in the world — stub returns False.
        return json.dumps(False)


# --------------------------------------------------------------------------- #
# Entry point (stdio)
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    mcp.run(transport="stdio")
