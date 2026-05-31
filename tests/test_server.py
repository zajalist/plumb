"""
Tests for cortex/server.py (Task 10) — FastMCP surface.

Tests:
1. Tool registry matches MCP_TOOLS keys exactly.
2. validate_operation tool on topple fixture returns a Verdict with stopped_at=stability.
3. bake_asset tool returns a PAP JSON.
4. Stub tools (sync_scene, commit, get_profile) return correct types.
5. check_collision returns a GateResult JSON.
"""

from __future__ import annotations

import asyncio
import sys
import os

import pytest

# Ensure repo root is on path so imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contracts import (
    MCP_TOOLS,
    Diff,
    GateName,
    Geometry,
    PAP,
    Physical,
    Semantics,
    Structural,
    Transform,
    Verdict,
)
from cortex.bake.physical import bake_physical
from cortex.world import WorldModel
from tests.helpers import make_box, two_part_topheavy, save_mesh_tmp


# ---------------------------------------------------------------------------
# Helpers (duplicated from test_orchestrator for self-containment)
# ---------------------------------------------------------------------------

def _square_footprint(half: float, center=(0.0, 0.0)) -> list[list[float]]:
    cx, cy = center
    return [
        [cx - half, cy - half],
        [cx + half, cy - half],
        [cx + half, cy + half],
        [cx - half, cy + half],
    ]


def _identity() -> Transform:
    return Transform(pos=[0.0, 0.0, 0.0])


def _make_topple_pap() -> PAP:
    """Top-heavy bronze figure PAP placed at pedestal edge — CoM ~7cm outside footprint."""
    parts, materials = two_part_topheavy()
    phys = bake_physical(parts, {0: materials["base"], 1: materials["body"]})
    footprint = _square_footprint(0.2, center=(-0.27, 0.0))
    return PAP(
        asset_id="bronze_figure",
        geometry=Geometry(
            aabb=[0.2, 0.2, 0.65],
            obb=[0.2, 0.2, 0.65],
            volume_m3=0.01,
            convex_parts=2,
        ),
        physical=Physical(mass_kg=float(phys.mass_kg), com=list(phys.com)),
        structural=Structural(support_footprint=footprint),
        semantics=Semantics(front=[0.0, 1.0, 0.0]),
    )


def _make_stable_pap() -> PAP:
    """A simple box PAP with CoM centred over its footprint — always stable."""
    return PAP(
        asset_id="stable_box",
        geometry=Geometry(
            aabb=[0.3, 0.3, 0.5],
            obb=[0.3, 0.3, 0.5],
            volume_m3=0.09,
            convex_parts=1,
        ),
        physical=Physical(mass_kg=10.0, com=[0.0, 0.0, 0.3]),
        structural=Structural(support_footprint=_square_footprint(0.3)),
        semantics=Semantics(front=[0.0, 1.0, 0.0]),
    )


# ---------------------------------------------------------------------------
# Import the server module (creates the FastMCP app)
# ---------------------------------------------------------------------------

import cortex.server as server_mod

mcp = server_mod.mcp


# ---------------------------------------------------------------------------
# Test 1: Tool registry matches MCP_TOOLS keys exactly
# ---------------------------------------------------------------------------

def test_tool_registry_matches_mcp_tools():
    """All keys in contracts.MCP_TOOLS must be registered as FastMCP tools."""
    async def _get_tools():
        tools = await mcp.list_tools()
        return {t.name for t in tools}

    registered = asyncio.run(_get_tools())
    expected = set(MCP_TOOLS.keys())
    assert registered == expected, (
        f"Tool registry mismatch.\n"
        f"  Missing from server: {expected - registered}\n"
        f"  Extra in server:     {registered - expected}"
    )


# ---------------------------------------------------------------------------
# Test 2: validate_operation on topple fixture → stopped_at=stability
# ---------------------------------------------------------------------------

def test_validate_operation_topple_fixture():
    """validate_operation via MCP returns Verdict with stopped_at=stability for topple."""
    pap = _make_topple_pap()
    world = WorldModel()
    world.add("figure", pap, _identity())

    diff = Diff(object="figure", transform=_identity())

    async def _call():
        result = await mcp.call_tool(
            "validate_operation",
            {
                "world_json": world.model_dump() if hasattr(world, "model_dump") else _world_to_dict(world),
                "diff_json": diff.model_dump(),
            },
        )
        return result

    result = asyncio.run(_call())
    # Extract content text
    content_text = result.content[0].text
    import json
    verdict_data = json.loads(content_text)
    assert verdict_data["ok"] is False
    assert verdict_data["stopped_at"] == "stability"
    # Gates list: collision ok, stability fail, constraints+reach skipped
    gates = verdict_data["gates"]
    assert len(gates) == 4
    assert gates[0]["gate"] == "collision"
    assert gates[0]["ok"] is True
    assert gates[1]["gate"] == "stability"
    assert gates[1]["ok"] is False
    assert gates[2]["gate"] == "constraints"
    assert gates[2]["skipped"] is True
    assert gates[3]["gate"] == "reach"
    assert gates[3]["skipped"] is True


# ---------------------------------------------------------------------------
# Test 3: bake_asset tool returns a PAP JSON
# ---------------------------------------------------------------------------

def test_bake_asset_tool_returns_pap():
    """bake_asset via MCP returns a PAP JSON with asset_id."""
    mesh = make_box(extents=(1.0, 1.0, 1.0))
    mesh_path = save_mesh_tmp(mesh, suffix=".obj")

    async def _call():
        result = await mcp.call_tool(
            "bake_asset",
            {
                "asset_id": "test_cube",
                "mesh_path": mesh_path,
            },
        )
        return result

    result = asyncio.run(_call())
    content_text = result.content[0].text
    import json
    pap_data = json.loads(content_text)
    assert pap_data["asset_id"] == "test_cube"
    assert "geometry" in pap_data
    assert "physical" in pap_data
    assert pap_data["geometry"]["watertight"] is True


# ---------------------------------------------------------------------------
# Test 4: Stub tools (sync_scene, commit) return correct types
# ---------------------------------------------------------------------------

def test_stub_tools_return_expected_types():
    """sync_scene returns a list, commit returns a bool."""
    async def _call_sync():
        result = await mcp.call_tool(
            "sync_scene",
            {"selector": "*"},
        )
        return result

    async def _call_commit():
        diff = Diff(object="figure", transform=_identity())
        result = await mcp.call_tool(
            "commit",
            {"diff_json": diff.model_dump()},
        )
        return result

    import json
    sync_result = asyncio.run(_call_sync())
    sync_data = json.loads(sync_result.content[0].text)
    assert isinstance(sync_data, list)

    commit_result = asyncio.run(_call_commit())
    commit_data = json.loads(commit_result.content[0].text)
    assert isinstance(commit_data, bool)


# ---------------------------------------------------------------------------
# Test 5: check_collision returns GateResult JSON
# ---------------------------------------------------------------------------

def test_check_collision_stable_box():
    """check_collision on an isolated stable box returns ok=True."""
    pap = _make_stable_pap()
    world = WorldModel()
    world.add("box", pap, _identity())

    async def _call():
        result = await mcp.call_tool(
            "check_collision",
            {
                "world_json": _world_to_dict(world),
                "a": "box",
                "b": None,
            },
        )
        return result

    import json
    result = asyncio.run(_call())
    gate_data = json.loads(result.content[0].text)
    assert gate_data["gate"] == "collision"
    assert gate_data["ok"] is True


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _world_to_dict(world: WorldModel) -> dict:
    """Serialize a WorldModel to a plain dict for the MCP tool call."""
    nodes = {}
    for nid in world.nodes():
        node = world.get(nid)
        nodes[nid] = {
            "pap": node.pap.model_dump(),
            "transform": node.transform.model_dump(),
            "parent": node.parent,
        }
    return {"nodes": nodes}
