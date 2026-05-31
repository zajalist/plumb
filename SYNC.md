# SYNC — node taxonomy + editor↔scene sync (design brainstorm)

Living design doc for two linked problems in the studio node editor. **No code yet.**

## The two problems (raised 2026-05-31)
1. **Categorization** — the palette (~15 specific items) is cluttered. Wrong taxonomy.
2. **Editor ↔ 3D sync** — importing/baking an object changes nothing in the node editor.

**Why they're one problem:** per the spec the graph doesn't hold "asset nodes" — assets live
in the world model and the graph *references* them. So fixing categorization (what a node *is*)
and fixing sync (how objects reach the graph) are the same decision.

> Disconnect is **normal/by-design today**: the editor runs on a hardcoded `INITIAL_SCENE`
> ([studio/src/lib/engine.ts](studio/src/lib/engine.ts)); imports live in a separate `assets[]`
> in [studio/src/App.tsx](studio/src/App.tsx). The two stores never touch.

---

## Decisions locked in this brainstorm

### D1 — Keep the `Object → Measure → Law → Verdict` flow. It's coherent.
It *is* the spec's `.wdf` "sentence" (§12.1: noun → measured relation → law → verdict),
collapsed. The flow was never the problem — the clutter was. **Don't redesign the flow.**

### D2 — Abstract the nodes; specifics go in the inspector.
The clutter came from flattening *(role × specific-op)* into separate palette items. Collapse
to **5 abstract role-nodes**; the inspector picks the spec-family specific (Q5 → option *c*):

| Node | Role | Inspector picks (spec family) | Eats today's items |
|---|---|---|---|
| **Object** | the noun | a baked asset (**dropdown**) or selector (byClass/byTag/onSurface) — §9.1/9.2 | all asset items + selectors |
| **Measure** | a reading | distance · clearance · comOverFootprint · angle · loadPath · sightline — §9.3/9.4 | comOverFootprint, convex clearance, angle→front, keep_clear, path_clear |
| **Law** | a constraint sink | relation + tolerance + hard/soft — §9.5 | stable, no-clip, facing, door-clear, walkway |
| **Field** | environment context | season / time / weather — §12.1 | field |
| **Verdict** | terminal roll-up | (auto) — §13 | verdict |

```
BEFORE: ~15 palette items (assets + ops + laws + verdict)
AFTER:  Object · Measure · Law · Field · Verdict   (5)
```

### D3 — Two layers: per-asset *behaviour* vs per-scene *intent*.
The spec separates the **Asset Studio (§8)** / **bake profiles (§6)** from the **node editor (§9)**.
Keep that separation:

- **Layer A — Behaviour (per asset, authored on the Object's inspector / Asset Studio).**
  Reused across scenes; enriches the PAP. Houses **both teammate ideas**:
  - **Articulation / "ouverture"** — door opening angles (45/90/180°) → swept volume.
    Spec §6 (articulated), `.wdf` `joint:{axis,range}` §12.2, DECISIONS Q17. → **WP-6**.
  - **Placement distribution** — array of tagged planes (floor/table/wall) + rest-state +
    terrain-noise statistical placement. Spec §8.1 `buried⚙` (terrain-stats→pose regression),
    §8.2 regions. → **WP-8**.
  - (+ materials/WP-5, rest states.)
- **Layer B — Scene intent (per scene, the node canvas).** The 5 abstract nodes from D2.

Behaviour **feeds** intent: e.g. door opening angle → swept volume → the `door_clear` **Law**
checks collision against it. Authored in different places; connected by data.

### D4 — "placement distribution" and "ouverture" are NOT Law nodes.
They are per-asset behaviour (Layer A). Earlier open question resolved: they enrich the asset,
they don't wire to the Verdict. (Matches §8 vs §9.)

### D5 — Object surface sampling (the math under placement distribution)
The placement engine doesn't drop the object at a single hand-set point — it **samples points
on the target surface and projects them onto the real geometry** to get an exact contact point
**+ surface normal**, then places/orients to it. (Chosen: sample the *target* surface —
plane/table/terrain — not the object's own mesh; own-mesh sampling for attach-sockets is later.)

- **One engine, two modes** (same primitive, N=1 vs N>1):
  - **snap-one** — place a single object precisely (correct Z + slope-aligned tilt on uneven ground).
  - **scatter-many** — distribute N instances across the surface (`populate`).
- **Pipeline:** sample on surface (strategy) → project onto geometry (raycast / closest-point) →
  contact point + normal → place + orient to normal (+ optional variance).
- **Sampling strategies:** uniform grid · jittered grid · **Poisson-disk / blue-noise** (default
  for scatter — even spacing, no clumping) · density/region-weighted.
- **Terrain:** project each sample onto the local heightmap → exact Z + tilt; per-member noise
  gives natural variation. This *is* spec §8.1 `buried⚙` (terrain-stats → pose, with variance).
- Lives in **Layer A**, powers **WP-8**, and feeds the MCP statistical-placement call.

---

## Sync model (answers Q1, Q2, Q4)

**One shared scene store** replaces the two stores (`assets[]` + `INITIAL_SCENE`). It holds
imported/baked assets (+ PAPs), their placements, and the graph. Single source of truth (§3/§7).

- **Object node's dropdown is populated from the store.** Import & bake → the asset appears in
  every Object dropdown automatically. **That is the sync.**
- **Q1 (auto-spawn?)** — **No.** Make it *available* in the dropdown; don't auto-build a chain.
  Respects §8.3 "progressive disclosure — hide nodes until earned."
- **Q2 (direction?)** — the graph **pulls** the asset list from the store; the panel doesn't push.
- **Q4 (delete/re-bake/material-confirm?)** — mutating the store refreshes dropdowns + live
  measures for free.

### Integration question (engine.ts vs real backend) — phase it
Don't rip out `engine.ts` mid-build. Source the **list** from the real store first; swap
**numbers** then **law evaluation** to the backend incrementally (so the demo never breaks).

---

## Phased plan (no code yet — this is the sequence we'll follow)

- **P0 · Declutter (frontend only, no backend).** Replace ~15 palette items with the 5 abstract
  nodes (D2); move specifics into inspector dropdowns. `engine.ts` keeps computing. *Done = the
  palette shows 5 nodes and the Gallery graph still evaluates.*
- **P1 · Sync the list.** One shared scene store; Object dropdown reads imported/baked assets;
  import → appears in dropdown, nothing auto-spawns. *Done = bake `test_figure.obj`, it's
  selectable in an Object node.*
- **P2 · Real numbers.** Selected Object's mass/CoM come from the real `/bake` PAP; Measures read
  it. *Done = the Object's `comOverFootprint` shows its own baked margin, not the canned −7cm.*
- **P3 · Behaviour authoring (Layer A).** Object inspector gains **Articulation** (door angles →
  swept wedge in viewport = **WP-6**) and later **Placement distribution** (= **WP-8**).
- **P4 · Live verdict.** Law evaluation via real `/validate`; the graph animates green/amber/red
  (§11 "intent conscience").

---

## Question status
- **Q1** (auto-spawn vs available) → **resolved:** available in dropdown, no auto-spawn.
- **Q2** (source of truth) → **resolved:** one store, graph pulls.
- **Q3** (live PAP/verdict feeds nodes) → **resolved:** yes (P2/P4), spec §11.
- **Q4** (delete/re-bake updates) → **resolved:** store-driven refresh.
- **Q5** (taxonomy) → **resolved:** option *c* — 5 abstract role-nodes, inspector picks spec family.

## Still open (need a human call)
- **O1** — Is **Layer A authored in the Object's inspector**, or in a **separate Asset Studio
  view**? (Both spec-valid; affects UX, not the data model.)
- **O2** — Naming: keep friendly `Object/Measure/Law/Field` labels, or use literal spec terms
  (`Selector/Operator/Constraint`)? (Cosmetic; pick what reads better for the demo.)
- **O3** — Confirm P0 can land without disturbing Fara's `ConstraintGraph.tsx` internals.
