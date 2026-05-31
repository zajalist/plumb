# PLUMB ↔ Unreal MCP integration

Goal: an AI agent (Claude) **builds a forest in Unreal** with your existing Unreal MCP
(*hayba*) and **validates every placement** through PLUMB's MCP — collision-free, stable,
walkable, law-abiding — repairing placements that fail before they land.

The two servers run side by side. Claude orchestrates them:

```
        ┌─────────────── Claude (MCP client) ───────────────┐
        │                                                    │
   hayba MCP                                            plumb-cortex MCP
  (build/read the UE scene)                       (bake + validate + repair)
        │                                                    │
   Unreal Engine  ◀──────  place / move trees  ──────────────┘
                  ──────  read transforms  ───────▶  mirror into PLUMB, validate
```

PLUMB never writes to Unreal here — hayba owns the scene. PLUMB is the **physics
conscience**: it bakes the tree once, mirrors hayba's placements, and answers
"is this valid? if not, where should it go?"

---

## 1. Register plumb-cortex alongside hayba

Add PLUMB's stdio MCP server to the same client config that already has hayba
(`claude_desktop_config.json`, or Claude Code's `.mcp.json`):

```jsonc
{
  "mcpServers": {
    "hayba": { /* …your existing Unreal MCP… */ },

    "plumb-cortex": {
      "command": "D:/Hackathons/plumb/.venv/Scripts/python.exe",
      "args": ["-m", "cortex.server"],
      "cwd": "D:/Hackathons/plumb"
    }
  }
}
```

Restart the client. You should see both tool sets. PLUMB exposes (forest-relevant):
`bake_asset`, `register_ue_asset`, `place_asset`, `validate_node`, `validate_forest`,
`suggest_transform`, `forest_layout`, `export_forest`, plus the coordinate seam
`ue5_to_canonical` / `canonical_to_ue5`.

> Run it standalone to sanity-check: `D:/Hackathons/plumb/.venv/Scripts/python.exe -m cortex.server`
> (it blocks on stdio — Ctrl-C to exit). The studio backend on `:8000` is separate and not required for the MCP path.

---

## 2. The coordinate seam (the thing that makes it line up)

hayba speaks **Unreal space**: centimetres, left-handed, Z-up.
PLUMB validates in **canonical space**: metres, right-handed, Z-up.

You don't convert by hand. Two ways:

- **Pass UE coords straight in**: `place_asset(..., space="ue5", pos=<cm>, quat=<x,y,z,w>)`
  converts internally. This is the seamless path.
- **Explicit**: `ue5_to_canonical(pos, quat)` and `canonical_to_ue5(pos, quat)` — use the
  latter to push a repaired transform back to hayba (`canonical_to_ue5` returns
  `{location_cm, rotation_quat}`, ready for hayba's move/spawn).

Conversion is the proven adapter (negate-X mirror + ×100), self-checked by
`golden_roundtrip_ok()`.

---

## 3. The forest recipe (what Claude does)

**Once, up front — bake the tree:**
1. Get the tree mesh as a file PLUMB can read (`.glb`/`.obj`). If it's a UE asset,
   convert via the studio `.uasset → glTF` pipeline, or export it.
2. `bake_asset(asset_id="tree", mesh_path="…/tree.glb")` → PAP (mass, CoM, footprint, masks).
3. `register_ue_asset("tree", "/Game/…/SM_Tree")` (the package path hayba spawns).

**Per tree — build with hayba, validate with PLUMB:**
4. hayba: spawn/locate a tree → read its UE transform `(location_cm, rotation)`.
5. `place_asset("tree", "tree_07", pos=<cm>, quat=<…>, space="ue5")` — mirror it into PLUMB.
6. `validate_node("tree_07", laws_json=<FOREST_LAWS>)` → Verdict.
7. If `ok=false`: `suggest_transform("tree_07", "{}")` → canonical fix →
   `canonical_to_ue5(fix.pos, fix.quat)` → **hayba moves the tree** there →
   `place_asset(... space="ue5")` again → re-validate. (This is the never-a-bare-no loop.)
8. Repeat for the whole forest.

**Prove the whole scene:** `validate_forest(<FOREST_LAWS>)` → `{ok, n, failures:[…]}` —
every tree vs every other (collision/spacing), each stable, walkways clear.
`forest_layout()` / `export_forest("forest.json")` records the validated result.

---

## 4. Forest laws (`FOREST_LAWS`)

Pass these as the `laws_json` to `validate_node` / `validate_forest`. `free_standing` is
injected automatically by the forest tools (trees rest on terrain — stable wherever they
sit, only toppling on tilt/slope), but you can add spacing + a walkway:

```json
[
  { "law": "free_standing" },
  { "law": "min_spacing", "distance_m": 2.0 },
  { "law": "walkway", "walkway_poly": [[-20,-2],[20,-2],[20,2],[-20,2]] }
]
```

- **collision** (always on): no two trunks/canopies interpenetrate.
- **free_standing**: a tree is stable on flat ground anywhere; topples only when tilt or
  slope carries its CoM off its own base.
- **walkway**: an agent of radius 0.45 m can traverse the polygon between the trees (reach gate).
- add your own constraint laws (facing, spacing) — see `cortex/gates/constraints.py`.

---

## 5. Copy-paste task for Claude

> You have two MCP servers: **hayba** (build/read the Unreal scene) and **plumb-cortex**
> (bake + validate + repair). Build a small forest and make it physically valid.
>
> 1. Bake the tree once: `bake_asset(asset_id="tree", mesh_path="<path to tree.glb>")`,
>    then `register_ue_asset("tree", "<UE package path>")`.
> 2. For each tree you place with hayba: read its UE transform, mirror it with
>    `place_asset("tree", "<id>", pos=<cm>, quat=<…>, space="ue5")`, then
>    `validate_node("<id>", laws_json='[{"law":"min_spacing","distance_m":2.0}]')`.
> 3. If a verdict fails, call `suggest_transform("<id>","{}")`, convert the fix with
>    `canonical_to_ue5(...)`, move the tree there in hayba, and re-validate.
> 4. When all trees are placed, call `validate_forest(...)` and report the result.
>    Don't leave any tree with a failing verdict.

That's the demo: an AI-built Unreal forest that PLUMB proves is collision-free, stable,
and walkable — and repairs whatever isn't.
