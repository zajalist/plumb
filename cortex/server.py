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
# Mask tools (design 2026-05-31) — agents author + compute semantic masks.
# These share the on-disk mask store with the studio UI, so a mask added here
# shows up in the studio on its next GET /masks (and vice-versa).
# --------------------------------------------------------------------------- #
@mcp.tool()
def list_masks(asset_id: str) -> str:
    """List the masks currently stored for an asset.

    Returns
    -------
    JSON array of Mask objects.
    """
    from cortex.masks import store

    return json.dumps([m.model_dump() for m in store.list_masks(asset_id)])


@mcp.tool()
def add_mask(asset_id: str, name: str, archetype: str, data: dict,
             category: str = "custom") -> str:
    """Author a custom mask onto an asset (source = "mcp").

    ``archetype`` is one of categorical | scalar | vector | markers; ``data`` must match
    that archetype's shape (categorical: ``{"regions":[...]}``; scalar:
    ``{"per_part":{...},"range":[lo,hi]}``; vector: ``{"samples":[...]}`` or
    ``{"field":"gravity"}``; markers: ``{"points":[...],"lines":[...],"axes":[...]}``).

    Returns
    -------
    JSON of the stored Mask (raises on invalid data).
    """
    from cortex.masks.providers.custom import ingest

    return ingest(asset_id, name, archetype, data, category=category).model_dump_json()


@mcp.tool()
def compute_mask(asset_id: str, provider_key: str) -> str:
    """Run a server-side mask provider (e.g. a geometry mask) for an asset and store it.

    Image-based providers (HF / Gemini / Vultr) need rendered views and are not computable
    here; use the studio's ``POST /masks/{asset_id}/compute`` for those.

    Returns
    -------
    JSON of the stored Mask.
    """
    from cortex.masks import compute_for

    return compute_for(asset_id, provider_key).model_dump_json()


@mcp.tool()
def remove_mask(asset_id: str, mask_id: str) -> str:
    """Delete a mask from an asset's store.

    Returns
    -------
    JSON ``true`` if a mask was removed, ``false`` otherwise.
    """
    from cortex.masks import store

    return json.dumps(store.delete(asset_id, mask_id))


# --------------------------------------------------------------------------- #
# Forest tools (commit-once world-building) — let an agent populate a scene with
# baked assets, validate each placement against the others, and export the
# committed canonical layout to UE5 space for one headless materialisation pass.
# --------------------------------------------------------------------------- #
# asset_id -> UE StaticMesh package path (e.g. "/Game/PlumbImport/SM_Tree"), used by
# the headless UE pass to spawn the right mesh at each committed transform.
_ue_assets: dict[str, str] = {}


def _forest_laws(laws_json: str) -> list[dict]:
    """Parse the caller's laws and ensure the scene is treated as free-standing (objects
    on a ground plane), so a tree is stable wherever it sits and only topples on tilt."""
    laws: list[dict] = json.loads(laws_json) if laws_json else []
    if not any(spec.get("law") == "free_standing" for spec in laws):
        laws = [{"law": "free_standing"}, *laws]
    return laws


def _tf(pos: list[float], quat: Optional[list[float]] = None,
        scale: Optional[list[float]] = None, space: str = "canonical") -> Transform:
    """Build a canonical Transform from pos/quat/scale. ``space="ue5"`` converts an
    Unreal transform (cm, left-handed) into canonical (m, right-handed) via the proven
    adapter — so transforms straight out of the Unreal MCP line up with PLUMB's gates."""
    t = Transform(pos=list(pos), quat=list(quat or [0.0, 0.0, 0.0, 1.0]),
                  scale=list(scale or [1.0, 1.0, 1.0]))
    if space == "ue5":
        from conscience.ue5 import adapter

        t = adapter.ue5_to_canon_transform(t)
    return t


@mcp.tool()
def ue5_to_canonical(pos: list[float], quat: Optional[list[float]] = None) -> str:
    """Convert an Unreal transform (cm, left-handed, Z-up) → PLUMB canonical (m,
    right-handed, Z-up). Feed the Unreal MCP's location/rotation straight in to mirror a
    placement into PLUMB for validation. Returns JSON ``{"pos":[...], "quat":[x,y,z,w]}``."""
    from conscience.ue5 import adapter

    q = list(quat or [0.0, 0.0, 0.0, 1.0])
    return json.dumps({"pos": adapter.ue5_to_canon_point(list(pos)),
                       "quat": adapter.ue5_to_canon_quat(q)})


@mcp.tool()
def canonical_to_ue5(pos: list[float], quat: Optional[list[float]] = None) -> str:
    """Convert a PLUMB canonical transform (m, right-handed) → Unreal (cm, left-handed).
    Use it to push a repaired/validated transform back to the Unreal MCP. Returns JSON
    ``{"location_cm":[x,y,z], "rotation_quat":[x,y,z,w]}``."""
    from conscience.ue5 import adapter

    q = list(quat or [0.0, 0.0, 0.0, 1.0])
    return json.dumps({"location_cm": adapter.canon_to_ue5_point(list(pos)),
                       "rotation_quat": adapter.canon_to_ue5_quat(q)})


@mcp.tool()
def register_ue_asset(asset_id: str, ue_package_path: str) -> str:
    """Map a baked ``asset_id`` to its UE StaticMesh package path (``/Game/...``).

    The headless forest-build pass spawns this mesh at each committed transform. Call
    once per asset after baking it (the path is what UE's editor sees, not a file path).

    Returns JSON ``{"asset_id":..., "ue_package_path":...}``.
    """
    _ue_assets[asset_id] = ue_package_path
    return json.dumps({"asset_id": asset_id, "ue_package_path": ue_package_path})


@mcp.tool()
def place_asset(asset_id: str, node_id: str, pos: list[float],
                quat: Optional[list[float]] = None,
                scale: Optional[list[float]] = None,
                space: str = "canonical") -> str:
    """Instantiate a baked asset as a world node at a transform (Z-up).

    ``space="ue5"`` lets you pass an Unreal transform (cm, left-handed) **straight from
    the Unreal MCP** — it's converted to canonical for you, so the two tools stay in
    lock-step. Adds the node so the gate stack can see it (collision against the other
    trees, stability on the ground, …); re-placing the same ``node_id`` just moves it.
    Bake the asset first (``bake_asset``). Then ``validate_node`` it, repair with
    ``suggest_transform``, and ``commit``.

    Returns JSON ``{"node_id":..., "placed": true}`` (or an ``error``).
    """
    pap = _pap_store.get(asset_id)
    if pap is None:
        return json.dumps({"error": f"unknown asset {asset_id!r}; bake_asset it first"})
    tf = _tf(pos, quat, scale, space=space)
    if node_id in _world.nodes():
        _world.update_transform(node_id, tf)
    else:
        _world.add(node_id, pap, tf)
    return json.dumps({"node_id": node_id, "placed": True})


@mcp.tool()
def validate_node(node_id: str, laws_json: str = "[]") -> str:
    """Validate an already-placed node at its current transform against the whole world
    (collision with the other trees, stability, the laws, reach). The node-centric
    counterpart to ``validate_operation`` — no need to re-send a canonical transform after
    a ``place_asset(space="ue5")``.

    Returns the JSON :class:`~contracts.Verdict`, or ``{"error": ...}`` if ``node_id`` is
    not placed.
    """
    if node_id not in _world.nodes():
        return json.dumps({"error": f"node {node_id!r} not placed; place_asset it first"})
    laws = _forest_laws(laws_json)
    node = _world.get(node_id)
    diff = Diff(object=node_id, transform=node.transform)
    verdict = _validate_operation(_world, diff, laws)
    return verdict.model_dump_json()


@mcp.tool()
def remove_node(node_id: str) -> str:
    """Drop a placed node from the world (e.g. a rejected placement). JSON ``true``/``false``."""
    try:
        _world.remove(node_id)
        return json.dumps(True)
    except KeyError:
        return json.dumps(False)


@mcp.tool()
def clear_forest() -> str:
    """Reset the world to empty (start a fresh scene). Returns JSON ``{"cleared": n}``."""
    n = len(_world.nodes())
    for nid in list(_world.nodes()):
        _world.remove(nid)
    return json.dumps({"cleared": n})


@mcp.tool()
def forest_layout() -> str:
    """The current scene: every placed node with its asset, canonical transform, and UE
    package path (if registered). This is the committed layout the UE pass materialises.

    Returns JSON ``{"count": n, "placements": [{node_id, asset_id, ue_asset, pos, quat,
    scale, mass_kg}, ...]}``.
    """
    out = []
    for nid in _world.nodes():
        node = _world.get(nid)
        out.append({
            "node_id": nid,
            "asset_id": node.pap.asset_id,
            "ue_asset": _ue_assets.get(node.pap.asset_id),
            "pos": list(node.transform.pos),
            "quat": list(node.transform.quat),
            "scale": list(node.transform.scale),
            "mass_kg": node.pap.physical.mass_kg,
        })
    return json.dumps({"count": len(out), "placements": out})


@mcp.tool()
def validate_forest(laws_json: str = "[]") -> str:
    """Re-validate the WHOLE committed scene: each node against all others (collision +
    stability + the laws). Proves the AI-built forest is sound before export.

    Returns JSON ``{"ok": bool, "n": int, "failures": [{node_id, stopped_at, detail}, ...]}``.
    """
    laws = _forest_laws(laws_json)
    failures = []
    for nid in _world.nodes():
        node = _world.get(nid)
        diff = Diff(object=nid, transform=node.transform)
        verdict = _validate_operation(_world, diff, laws)
        if not verdict.ok:
            g = next((x for x in verdict.gates if x.gate == verdict.stopped_at), None)
            failures.append({"node_id": nid,
                             "stopped_at": verdict.stopped_at.value if verdict.stopped_at else None,
                             "detail": g.detail if g else None})
    return json.dumps({"ok": not failures, "n": len(_world.nodes()), "failures": failures})


@mcp.tool()
def export_forest(out_path: str) -> str:
    """Write the committed layout to ``out_path`` as JSON, with each transform converted
    to **UE5 space** (cm, left-handed, via the proven adapter) plus the UE asset path —
    ready for the headless ``tools/ue_build_forest.py`` materialisation pass.

    Returns JSON ``{"out_path":..., "count": n, "missing_ue_asset": [asset_ids...]}``.
    """
    from conscience.ue5 import adapter

    placements = []
    missing = set()
    for nid in _world.nodes():
        node = _world.get(nid)
        ue_asset = _ue_assets.get(node.pap.asset_id)
        if not ue_asset:
            missing.add(node.pap.asset_id)
        ue_t = adapter.canon_to_ue5_transform(node.transform)
        placements.append({
            "node_id": nid,
            "asset_id": node.pap.asset_id,
            "ue_asset": ue_asset,
            "location_cm": list(ue_t.pos),
            "rotation_quat": list(ue_t.quat),
            "scale": list(ue_t.scale),
        })
    doc = {"space": "ue5_cm_lh", "count": len(placements), "placements": placements}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2)
    return json.dumps({"out_path": out_path, "count": len(placements),
                       "missing_ue_asset": sorted(missing)})


# --------------------------------------------------------------------------- #
# Placement distributions — learned-by-example placement on tagged surfaces.
# The studio captures examples (place the asset against a reference surface); these
# tools serve the resulting distribution so an agent building in Unreal gets a
# physically-plausible pose for "on a table", "on terrain", … (generic, per-asset).
# --------------------------------------------------------------------------- #
@mcp.tool()
def add_placement_example(asset_id: str, tag: str, orientation: str = "horizontal",
                          normal_offset: float = 0.0, tilt_deg: float = 0.0,
                          yaw_deg: float = 0.0, lateral_json: str = "[0,0]",
                          noise_json: Optional[str] = None) -> str:
    """Record one demonstrated placement of an asset on a tagged reference surface.

    Frame is the surface's: ``normal_offset`` = signed distance of the asset origin along
    the surface normal (− = embedded/sunk), ``tilt_deg`` = lean off the normal, ``yaw_deg``
    = spin about it, ``lateral`` = [u,v] in-plane offset. ``tag`` is the surface semantics
    (floor / table / wall / terrain …). Returns the stored example JSON.
    """
    from cortex import placement_store

    ex = placement_store.add_example(asset_id, {
        "tag": tag, "orientation": orientation, "normal_offset": normal_offset,
        "tilt_deg": tilt_deg, "yaw_deg": yaw_deg,
        "lateral": json.loads(lateral_json) if lateral_json else [0.0, 0.0],
        "noise": json.loads(noise_json) if noise_json else None,
    })
    return json.dumps(ex)


@mcp.tool()
def place_on_surface(asset_id: str, surface_tag: str) -> str:
    """The learned placement of ``asset_id`` on a surface tagged ``surface_tag``.

    Aggregates the demonstrated examples for that tag into a distribution and returns the
    **mean** pose, its **spread**, and one **sampled** draw — all in the target surface's
    frame (apply relative to the actual surface normal/point in Unreal). E.g. a tree whose
    mesh includes roots gets a believable negative ``normal_offset`` (root sink) + slope
    tilt on "terrain". Returns ``{"error": ...}`` if no examples are tagged ``surface_tag``.
    """
    import random

    from cortex import placement_store

    dist = placement_store.distribution(asset_id, surface_tag)
    if dist is None:
        have = placement_store.tags(asset_id)
        return json.dumps({"error": f"no '{surface_tag}' examples for {asset_id!r}",
                           "available_tags": have})
    m, s = dist["mean"], dist["spread"]
    sampled = {
        "normal_offset": m["normal_offset"] + random.gauss(0.0, s["normal_offset"]),
        "tilt_deg": m["tilt_deg"] + random.gauss(0.0, s["tilt_deg"]),
        "yaw_deg": m["yaw_deg"] + random.gauss(0.0, s["yaw_deg"]),
        "lateral": [m["lateral"][0] + random.gauss(0.0, s["lateral"][0]),
                    m["lateral"][1] + random.gauss(0.0, s["lateral"][1])],
    }
    return json.dumps({**dist, "sampled": sampled})


@mcp.tool()
def placement_tags(asset_id: str) -> str:
    """The surface tags this asset has demonstrated placements for → example count. JSON dict."""
    from cortex import placement_store

    return json.dumps(placement_store.tags(asset_id))


@mcp.tool()
def export_placement_wdf(out_path: Optional[str] = None, asset_ids_json: Optional[str] = None,
                         scene_name: str = "placement") -> str:
    """Export the learned placement language as a ``.wdf`` document — the portable PLUMB
    language. Each asset becomes a vocabulary noun; each surface distribution becomes a
    soft ``settle_on`` law (sink + tilt mean/spread). Pass ``asset_ids_json`` (a JSON
    array) to pick assets, else every asset with captured examples is included. If
    ``out_path`` is given the ``.wdf`` is written there (the studio can File→Open it).

    Returns JSON ``{"wdf": "<text>", "out_path": ..., "assets": [...]}``.
    """
    from cortex import placement_store

    ids = json.loads(asset_ids_json) if asset_ids_json else placement_store.all_assets()
    text = placement_store.to_wdf(ids, scene_name=scene_name)
    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(text)
    return json.dumps({"wdf": text, "out_path": out_path, "assets": ids})


# --------------------------------------------------------------------------- #
# Entry point (stdio)
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    mcp.run(transport="stdio")
