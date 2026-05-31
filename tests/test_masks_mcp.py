"""Tests for the cortex MCP mask tools + custom ingest (Phase D)."""

from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cortex.server as server_mod
from cortex.masks import store
from cortex.masks.providers import custom

mcp = server_mod.mcp


def _text(result):
    return result.content[0].text


def test_add_list_remove_via_tools(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "BAKES_DIR", tmp_path / "bakes")

    async def _run():
        added = await mcp.call_tool("add_mask", {
            "asset_id": "mcp_asset", "name": "Load-bearing", "archetype": "markers",
            "data": {"points": [{"pos": [0, 0, 1], "label": "load", "kind": "support"}]},
            "category": "custom",
        })
        listed = await mcp.call_tool("list_masks", {"asset_id": "mcp_asset"})
        return added, listed

    added, listed = asyncio.run(_run())
    m = json.loads(_text(added))
    assert m["source"] == "mcp" and m["archetype"] == "markers" and m["id"] == "load_bearing"

    masks = json.loads(_text(listed))
    assert len(masks) == 1 and masks[0]["id"] == "load_bearing"

    removed = asyncio.run(mcp.call_tool("remove_mask", {"asset_id": "mcp_asset", "mask_id": "load_bearing"}))
    assert json.loads(_text(removed)) is True
    assert store.list_masks("mcp_asset") == []


def test_add_mask_rejects_bad_data(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "BAKES_DIR", tmp_path / "bakes")
    # scalar archetype with no per_part → validation error surfaces
    try:
        asyncio.run(mcp.call_tool("add_mask", {
            "asset_id": "mcp_asset", "name": "bad", "archetype": "scalar", "data": {}}))
        raised = False
    except Exception:
        raised = True
    assert raised


def test_custom_seed_grasp_points(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "BAKES_DIR", tmp_path / "bakes")
    m = custom.seed_grasp_points("seed_asset", [[0, 0, 1], [0.1, 0, 1]])
    assert m.id == "grasp_points" and m.archetype == "markers"
    assert len(store.list_masks("seed_asset")) == 1
