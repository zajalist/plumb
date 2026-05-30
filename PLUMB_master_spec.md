# PLUMB — Master Specification

**A spatial cortex and a language for physically-grounded, intent-aware 3D worlds.**

> Working name. *PLUMB* — a plumb line is the oldest tool for testing whether something hangs **true** under gravity. That is what this system does for an AI's spatial decisions: nothing commits to the world until it has been proven physically and intentionally true. Rename freely.

This is the single source of truth for the project. It consolidates the concept, the full architecture, every subsystem (baking, type-aware bake profiles, the asset studio, the constraint node editor, the validation gates, observability), the `.wdf` file language, the competitive research, the ranked technical risks, the architecture optimizations, and the staged build plan. A running example scene — **"The Gallery"** — threads through so nothing stays abstract.

---

## Table of Contents

1. Executive Summary
2. The Problem
3. The Mental Model
4. System Architecture
5. Subsystem A — The Bake Pipeline
6. Bake Profiles — Type-Aware Baking (archetype catalog)
7. Subsystem B — Canonical World Model + UE5 Adapter
8. Subsystem C — The Asset Studio
9. Subsystem D — The Constraint Node Editor
10. Subsystem E — The Validation Cortex (gates + MCP tools)
11. Subsystem F — Observability
12. The World Language (`.wdf`)
13. Data Contracts
14. Use Cases & Flows
15. The Flagship Demo
16. Competitive Landscape (what to steal, how PLUMB differs)
17. Technical Risks & Mitigations (ranked)
18. Architecture Optimizations
19. Novelty & Positioning
20. Build Roadmap
21. Tech Stack
22. Appendix — Glossary & Pitch Lines

---

## 1. Executive Summary

LLM agents driving 3D environments are *spatially blind*: they emit transforms from textual priors and discover failure only after the fact — objects inside walls, floating assets, unstable stacks, blocked doors, broken sightlines. Existing 3D MCP servers are **actuators** (muscle without a brain); academic physics-grounding frameworks prove the brain works but are monolithic, single-purpose research pipelines.

PLUMB is the missing layer. It sits between any agent and a 3D engine (Unreal Engine 5 first) and does five things no current tool combines:

1. **Bakes** every asset into a rich, reusable *Physical Asset Profile* before the agent is allowed to use it — and bakes are **type-aware** (a door, a tree, and a shelf get different recipes).
2. Lets humans **author intent** — artistic *and* scientific — through a visual constraint node graph.
3. Lets humans **author behaviour** — how an asset can sit, what attaches to it — in an Asset Studio by demonstration.
4. **Validates** every proposed change through gates that return not just *no* but the exact number it failed by and the gradient direction to fix it.
5. Compiles all of it into a single portable **`.wdf` file** — a declarative *language* for physically-grounded worlds.

The defensible contribution is not "LLM + physics + layout" (academia already does that) nor "MCP for a DCC" (several servers exist). It is the **integration**: cached, provenance-tracked, type-aware asset understanding + a visual intent/behaviour authoring layer + a composable validation API + a portable world-description language, with full observability. **glTF and USD describe geometry; `.wdf` describes meaning, physics, and intent.**

---

## 2. The Problem

Foundation models are trained on textual abstractions of the physical world, not grounded spatial reality. When asked to reason about 3D layout, proximity, support, or kinematics they hallucinate physically impossible operations with full confidence. Empirically (Holodeck, LayoutGPT), an LLM that **emits numeric coordinates directly** produces overlapping/floating layouts, whereas an LLM that **emits relational constraints fed to a solver** produces plausible ones. The fix is therefore not a better prompt; it is a *grounding loop* — propose, validate against real computation, repair, commit — plus an asset layer that actually knows what each object is (a hollow glass vase vs. a solid bronze figure are physically nothing alike, but identical to a naive geometry pass).

Today's correction loop is also expensive: without local validation, an agent round-trips to the engine and burns context tokens guessing until something looks right. PLUMB moves validation into a fast local cortex so the agent converges in a couple of steps with hard numbers.

---

## 3. The Mental Model

**Three nouns, one loop.**

- **Profiles** — *what each object is.* Bake an asset once into a Physical Asset Profile (PAP): geometry, material/composition, mass, centre of mass, inertia, affordances, structural limits, rest states. Cached, versioned, human-overridable.
- **Constraints** — *what you want.* Author intent (artistic + scientific) in a visual node graph. Each constraint compiles to a cost function with a tolerance.
- **Gates** — *what's true.* Every proposed change runs a gauntlet (Collision → Stability → Constraints → Reachability) and halts at the first hard failure.

The loop: **Bake → Author → Propose → Gate → Repair → Commit.**

**The one technical idea that unifies the system:** every gate's check is *also* a cost function. "Pass" = cost ≤ tolerance; the violation magnitude *is* the cost; the gradient of that cost *is* the "which way to move to fix it" arrow. Therefore **validation and repair are the same maths** — the function that rejects a placement is the exact function `suggest_transform` minimises to repair it. This is why PLUMB can always answer *why* and *how*, not just *no*, and why the entire UI is "the verdict, drawn."

---

## 4. System Architecture

Six subsystems connected by one canonical world model:

```
                    ┌──────────────────────────────────────────┐
                    │                AGENT (LLM)                │
                    │  propose → validate → diagnose → repair   │
                    └───────────────┬──────────────────────────┘
                                    │ MCP (FastMCP)
   ┌────────────────────────────────┴───────────────────────────────────┐
   │                          PLUMB CORTEX (Python)                       │
   │  ┌──────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐  │
   │  │ BAKE     │  │ CANONICAL    │  │ CONSTRAINT   │  │ ASSET       │  │
   │  │ PIPELINE │─▶│ WORLD MODEL  │◀─│ COMPILER     │  │ STUDIO      │  │
   │  │ +profiles│  │ (shadow)     │  │ (node graph) │  │ (states/    │  │
   │  └────┬─────┘  └──────┬───────┘  └──────────────┘  │  regions)   │  │
   │       ▼ PAP            ▼                            └─────────────┘  │
   │  ┌──────────┐  ┌──────────────┐                                     │
   │  │ ASSET DB │  │ VALIDATION   │   fcl · recast · mujoco · constr.    │
   │  │ +override│  │ CORTEX       │   → verdict (numbers + fix vector)   │
   │  └──────────┘  └──────┬───────┘                                     │
   └──────────────────────-┼─────────────────────────────────────────────┘
                           │ logs all
              ┌────────────┴───────────────┐
              │ OBSERVABILITY (Rerun + UI)  │
              └────────────────────────────┘
                           ▲
              UE5 ADAPTER (C++ Automation Bridge)
                           ▲
              UNREAL ENGINE 5 (renderer + Chaos)

   Everything serialises to / loads from a single .wdf file.
```

The agent never talks to UE5 directly. It talks to the cortex; the cortex validates; only validated diffs reach the engine.

---

## 5. Subsystem A — The Bake Pipeline

Baking is the pre-flight that makes physical reasoning *honest*. Before an asset can enter a scene it is compiled into a **Physical Asset Profile (PAP)** — a cached, versioned sidecar. Baking runs in stages, cheapest first.

### 5.1 Geometric bake (deterministic)
Watertight check; axis-aligned and oriented bounding boxes; volume; surface area; **convex decomposition via CoACD** (Collision-Aware ACD), *not* V-HACD. V-HACD is end-of-life and is documented to fill holes/slots, which would silently corrupt both collision and affordance reasoning — e.g. it would fill the vase's opening and treat it as a solid lump. CoACD preserves fine concavity. The convex parts serve as collision proxies and as the substrate later stages reason over per-part.

### 5.2 Semantic bake (VLM / classifier)
Render the asset from several angles and infer: object class, canonical **up** and **front** vectors, **per-part material composition**, and **affordances/sockets** (seatable, stackable, grasp point, attachment). Use the PhysX-line schema (five dimensions: absolute scale, material, affordance, kinematics, function) as the back-end so it is citable and standardised rather than bespoke. Every field carries a **confidence**. The `front` vector drives artistic facing constraints; affordances tell the agent *where* placement is even legal; material feeds the physical bake.

### 5.3 Physical bake (composition-aware)
Assign densities to parts from a material table → compute **mass, centre of mass, and the full inertia tensor** over the *density-weighted* convex parts (not the naive uniform-density centroid). Detect **hollowness** via interior ray tests. This is what stops the agent confidently balancing a heavy bronze figure on a plinth's edge — PLUMB knows the CoM is high and forward — and what makes "don't stack on the hollow vase" enforceable (low mass → low load capacity).

### 5.4 Structural bake (experimental — prior, never ground truth)
Support footprint (hull of ground-contact points), coarse stiffness/Young's-modulus estimate, estimated max load, obvious weak points (thin necks, cantilevers). Single-asset stiffness/material inference is unreliable in 2025–26 (see §17), so these are surfaced as **priors with wide confidence bands** and are **never hard-gated**. Treating them honestly is itself a credibility feature.

### 5.5 The PAP — the reusable artifact
Bake once, reuse across every scene. Every field is overridable with a **lock** and a **confidence chip**, and edits are recorded in **provenance** (`auto` vs `edited`, with `locked` fields). Re-baking is incremental and respects locks. This caching + provenance + human-override loop is the thing research pipelines lack — they recompute per scene; PLUMB makes asset understanding a durable, trustworthy artifact.

```json
{
  "asset_id": "bronze_figure_03",
  "bake_version": 3,
  "profile": "rigid_prop",
  "geometry": { "obb": [...], "volume_m3": 0.031, "convex_parts": 9, "watertight": true },
  "semantics": { "class": "statue", "up": [0,0,1], "front": [0,1,0],
                 "materials": [{ "part": "body", "mat": "bronze", "conf": 0.82 }],
                 "affordances": ["base_contact@[...]"], "conf": 0.8 },
  "physical": { "mass_kg": 48.0, "com": [0,0.04,0.71], "inertia": [[...]], "hollow": false, "conf": 0.7 },
  "structural": { "support_footprint": [...], "max_load_kg_est": null, "experimental": true },
  "rest_states": ["upright", "fell", "buried⚙"],
  "regions": [],
  "provenance": { "auto": true, "edited_fields": ["physical.mass_kg"], "locked": ["physical.mass_kg"] }
}
```

---

## 6. Bake Profiles — Type-Aware Baking

A bake is **not one recipe.** PLUMB detects what an asset *is* (from the semantic pass) and loads a **Bake Profile**: a tailored set of specialised passes, default rest states, default sockets/regions, and default constraints for that archetype. Drop a tree and PLUMB already knows about seasons, tap-sockets, root-on-terrain, and canopy spacing; drop a door and it already knows its swing arc must stay clear. The agent inherits all of it for free, and the gates enforce it. **This type-awareness is the moat.**

### 6.1 The mechanism
A Bake Profile = `detector → specialised passes → default repertoire (states/regions) → default constraints → tunable params`, all overridable behind progressive disclosure. A boring crate inherits the "rigid prop" profile untouched; a hero asset gets fine-tuned. A **Profile Editor** lets a technical artist author *new* archetypes — so the system scales to any asset type instead of a hardcoded list. That extensibility is itself a pitch point.

Also note the second reframe that makes this an **environment** bake: a bake is not just about the object in isolation but about how it *participates* — what it connects to, what it hosts, what space it needs to function, how the surroundings change it. That relational layer is the differentiator, and it still reduces to the four currencies (states, regions, fields, constraints), so it stays clean.

### 6.2 Archetype catalog

| Archetype | Examples | Signature bake | Environment payoff |
|---|---|---|---|
| **Containers / holders** | shelf, basket, crate, bottle, drawer, bowl | capacity bake: interior volume, fill regions, what-fits manifest, count/weight limits, opening direction | shelves advertise validated slots; `populate()` fills correctly; bottle knows its fill line |
| **Furniture / usable** | chair, table, bed, desk | usage-volume bake: support surfaces + load limits **+ the clearance you must leave to use it** (legroom, chair pull-out, drawer-open), arrangement grammar | agent can't shove a chair against a wall it can't be sat in |
| **Modular / kit-bash** | walls, floors, fences, pipes, road tiles | connector bake: snap sockets, mating faces, allowed-neighbour adjacency grammar, seam/material continuity | the LEGO of levels — procedural assembly correct by construction |
| **Articulated / kinematic** | door, drawer, lever, valve, lid, laptop | swept-volume bake: joint axes + limits, **the space the moving part needs** → keep-clear, open/closed/ajar states | *demo gold:* agent refuses to block a door's swing arc |
| **Deformables** | curtain, rug, cable, chain, banner, tablecloth | drape & route bake: precomputed drape onto host shapes, pins/anchors, slack/tension, conform-to-surface | cables route between sockets; tablecloth drapes over any table; rug conforms to floor |
| **Liquids / granular** | water, puddle, sand pile, grain, snow | fill & settle bake: container fill-level, granular angle-of-repose, surface-conformity | pour → finds level; spill → pools in terrain dips |
| **Vegetation / organic** | tree, bush, crop, coral, mushroom | growth + socket + ecology bake: season/age states, paintable attach-bands (fruit, nests, **taps, hives, lanterns**), root-flare footprint, sway, ecological placement (sun/water/soil, canopy spacing, species adjacency, density vs slope) | forests scatter by ecological rules; one slider repaints the season |
| **Terrain / ground** | heightfield, cliff, beach, riverbed, path | surface-host bake: walkability/slope/friction, footstep-material, **the receiving side of rest states** (sand vs rock changes burial); erosion → where water/sediment/puddles/vegetation land | terrain & objects *handshake*: burial regression reads terrain surface-type |
| **Lights / emitters** | lamp, window, fire, neon, screen | photometric bake: range/cone/colour/flicker, coverage + what it illuminates, mounting sockets, clearance-from-flammable, day/night/off states | lighting becomes a constraint *target* ("light the plaque", "no dark stretch") |
| **Acoustic emitters** | fountain, machinery, crowd, radio | acoustic bake: emission profile, falloff, wall occlusion | soundscape constraints — even coverage, no dead zones, quiet-zone respect |
| **Gameplay-functional** | cover, pickup, ladder, jump pad, spawn, objective | affordance bake: cover height/angle vs sightline graph, jump-reachability arcs, climb volumes, pickup reach | gates *prove* objectives reachable & cover fair — verified level design |
| **Vehicles / platforms** | car, cart, elevator, lift | dynamic-envelope bake: turning radius, parking footprint, ingress/egress space, swept motion volume | park where it fits *and* can exit; moving platform path stays clear over time |
| **Characters / crowds** | NPC, creature | agent bake: nav radius/height, reach/sit/grab anchors that must *match* furniture affordances, social spacing, queue formation | crowds fill a plaza with believable spacing; NPC only sits where its rig fits |
| **Decals / weathering** | moss, rust, dirt, crack, leak, graffiti | contextual-placement bake: rules that read the environment (moss on damp/north faces, rust near water+metal, wear on high-traffic edges) | the purest *environment* bake — the surroundings decide where detail belongs |
| **Composite / hero props** | dressed desk, market stall, campfire | assembly bake: sub-part hierarchy, posable parts, internal constraints, stampable "dressed" preset | stamp a believable cluster; agent jitters it without breaking internal logic |

### 6.3 Cross-cutting "environment" dimensions
Toggleable layers any archetype can carry — this is what makes the bake *environmental*:

- **Connectivity** — sockets / snaps / adjacency grammar (who attaches to whom).
- **State sets** — season / time-of-day / weather / wet-dry / on-off variants, parametric.
- **Wear & age** — pristine → worn → broken, *and* contextual wear keyed to traffic.
- **Distribution** — density, clumping, slope/altitude/biome rules for scatter.
- **Fields** — light, acoustic, thermal/airflow coverage as constraint surfaces.
- **Budget** — poly / texture / draw-distance / instancing limits, so the agent respects performance (a real shipping constraint nobody demos).
- **Narrative** — "looted", "abandoned", "ceremonial" bias the states (a *looted* shelf bakes half-empty with fallen items).

### 6.4 The four demo-gold bakes (pick these to win)
1. **Door swing-volume keep-clear** — visceral, instantly legible, uniquely "physical reasoning." Place furniture; the agent protects the arc.
2. **Seasonal ecological forest** — one slider repaints a whole forest scattered by sun/slope/spacing rules, trees carrying tap/hive sockets.
3. **Looted / abandoned shelf** — drag a narrative tag, contents re-pose to fallen/missing while staying physically valid.
4. **Contextual weathering** — "the environment decided the moss goes here."

> **Scope discipline:** the 14 archetypes demonstrate that the *system generalises* — you do not build them all. The winning play ships the **Bake Profile architecture** (detect → load recipe → fine-tune) plus **three archetypes that look effortless** (door, tree, shelf). Judges extrapolate the rest.

---

## 7. Subsystem B — Canonical World Model + UE5 Adapter

**Canonical space:** one rigid convention — **Z-up, right-handed, metres, kilograms** (matches physics convention and MuJoCo's gravity axis). The world model is a lightweight scene graph of nodes, each referencing a PAP plus a transform (position + quaternion + scale), parent, and attached constraints. It is the single source of truth the validator reasons over — a *shadow state* of the engine.

**UE5 adapter (the Hayba reuse):** UE5 is **left-handed, Z-up, 1 unit = 1 cm**. The adapter is the only place that knows this. UE5 → canonical: scale ×0.01, apply a handedness flip (mirror one axis, which inverts mesh winding → re-flip winding on the proxy so collision normals stay correct). Canonical → UE5 reverses it. Because Z-up is shared, there is **no 90° axis swap** — only handedness + scale, the cheap case. The existing UE5 MCP bridge becomes the transport: the C++ Automation Bridge extracts selected actors' transforms + bounding proxies and pushes them to the cortex; validated diffs return the same channel.

**Sync discipline (the hard part — handle explicitly):** continuous real-time sync from a live editor is the classic trap (latency, two-sources-of-truth drift). PLUMB makes sync **episode-scoped**: `sync_scene` pulls only tagged/relevant actors as bounding proxies in one batch (never the whole level, never high-poly meshes); the world model is authoritative *during a reasoning episode*; `commit` reconciles back with an **optimistic-concurrency guard** (hash the snapshot; refuse commit if UE5 changed). This sidesteps drift, latency, and editor version churn.

---

## 8. Subsystem C — The Asset Studio

The studio authors **behaviour** (per-asset repertoire), distinct from the node editor which authors **scene intent**. Everything you'd want here is one of two primitives, and the guiding principle is **demonstrate, don't configure.**

### 8.1 Primitive 1 — Rest States
A named pose defined by *how the object contacts a surface*. You author it by demonstration: drag the asset toward a reference plane and PLUMB auto-settles it with the physics engine; you nudge; it records the **contact frame + footprint + stability margin** automatically. You never type numbers.

- **upright** — one drag, rests on its base. Footprint = base. (table/floor/shelf)
- **fell** — rotate onto its side; PLUMB records the new contact patch + footprint. (debris/narrative)
- **leaning** — give a ground plane *and* a wall plane; both contacts recorded.
- **buried (⚙ parametric)** — author-by-exemplar regression. Provide a few terrain *exemplars* (planes carrying different heightmap noise: smooth sand, gravel, rocky); for each, pose how deep/tilted the object settles. PLUMB fits a mapping from **terrain statistics (RMS height, correlation length, local slope) → pose parameters (burial depth, orientation)**. At placement time it evaluates that mapping against the actual surrounding heightmap to get the expected pose **with variance**, so instances look naturally varied rather than cloned. (Same probabilistic-placement idea PhyScensis uses for stability, reused for burial.) UX: exemplar thumbnails, a roughness slider that previews the pose morphing, and a "scatter test" that drops ~16–20 instances so you eyeball the distribution before trusting it.

### 8.2 Primitive 2 — Regions
A zone you **paint** on the mesh (or on a state's contact plane), tagged with a type that carries a rule:

- **Fill region** (shelf) — paint the surface; set a packing rule (grid / jitter / lean), allowed asset tags, density. Feeds a validated `populate(region, assets)` op — every placement it generates still runs the gates.
- **Attach socket** (tree) — paint a trunk band → "accepts: tap, height 0.5–1.5m, oriented outward, min-spacing 30cm"; paint a branch → "accepts: beehive, hangs, count 0–2." The rule lives with the painted region.
- **Contact patch** — usually auto-derived from a rest state, editable.
- **Keep-clear** — zones that must stay unobstructed (chair seat, front of an appliance) → become hard constraints.

Each painted region becomes a **typed node** in the graph, so painting and the node canvas are the same system — the paint *produces* the node you then wire rules into.

### 8.3 The streamlining principles (the UX answer)
- **Demonstrate, don't configure.** Every case is "show PLUMB an example, it generalises" — drag to pose, paint to region, place a few exemplars to fit burial, drop one arrangement to teach packing. The user never edits a regression coefficient. This consistency makes a vase, a shelf, and a tree feel like *the same tool*.
- **Progressive disclosure — hide the nodes until earned.** A boring asset needs zero nodes (auto "upright" from the up-vector). The node canvas only appears for the **⚙** items needing conditional power (burial-vs-terrain, fill rules, attach constraints). Beginners never see a graph; power users get all of it. This is the single biggest thing protecting against node-soup.
- **Typed authored-items as currency.** States and Regions are first-class typed objects; that lets a Fill node accept a `Region`, a Buried node accept `HeightmapProfile`s, an Attach node accept a `Socket` — and keeps the graph legible.
- **Validate in-studio.** A test mode drops the asset in each authored state onto test surfaces and confirms stability using the *same* gate viz as the main app — so an authored state is guaranteed valid before it reaches a scene.

### 8.4 How it plugs into placement
At placement the agent **picks the rest state matching the narrative** ("knocked over" → `fell`) and the Stability gate validates against *that state's* footprint, so placement is correct by construction. Fill/Attach regions power validated `populate`. The buried regression is a parametric driver evaluated against the local heightmap. The studio feeds the exact systems already built; it is a richer **Repertoire** section on the PAP, not a separate world.

---

## 9. Subsystem D — The Constraint Node Editor

Author intent as a visual graph; the same graph expresses aesthetics and physics.

### 9.1 Node families
- **Selectors** — `byId`, `byClass("book")`, `byTag("fragile")`, spatial (`onSurface(shelf)`). Output type **Object**.
- **Properties** — pull PAP/transform fields: `mass`, `com`, `footprint`, `front`, `bbox`.
- **Geometric operators** — `distance`, `clearance`, `angleBetween`, `align`, `raycast/sightline`, `contains`, `onSurface`.
- **Physical operators** — `comOverFootprint` (stability margin), `loadPath`, `dropTest`.
- **Constraint sinks** — assert `relation(value, target, tolerance)`; emit **pass/fail + continuous violation magnitude + gradient**. Marked **hard** (gates commit) or **soft** (weighted objective for repair).

### 9.2 Typed ports
Ports are typed (Object → Vector → Scalar → Pass/Fail), so only valid wires connect — you cannot build a nonsense graph. This is also what makes painting-produces-a-node coherent.

### 9.3 Compilation
The graph lowers to an ordered list of weighted cost functions. Hard sinks → inequality gates; soft sinks → terms in the objective `suggest_transform` minimises. Constraints attach to an object (travel with its PAP) or to the scene. Prior art for "constraint = differentiable cost" includes ReKep (Python keypoint→cost functions) and LayoutVLM (per-constraint differentiable cost optimised jointly); the node editor is a *visual front-end* over the same idea, which is the UX differentiator.

### 9.4 The Gallery's graph (worked example)

| Intent | Nodes | Hard/soft | Reads from |
|---|---|---|---|
| Figure faces entrance ±8° | `front(bronze)` → `angleBetween(entrance)` → sink ≤ 8° | soft | semantics.front |
| Nothing floats | `byClass(*)` → `onSurface` → sink == true | hard | geometry |
| Stable (CoM over base) | `comOverFootprint(*)` → sink margin ≥ 2cm | hard | physical.com / footprint |
| Don't load the fragile vase | `byTag("fragile")` → `loadPath` → sink load ≤ cap | hard | structural / tags |
| Walkway ≥ 90cm | `path_clear(walkway, r=0.45m)` → sink == true | hard | navmesh |
| Lamp 30cm from flammable | `clearance(lamp, byTag("flammable"))` → sink ≥ 30cm | hard | geometry |
| Lamp lights the plaque | `sightline(lamp, plaque)` → sink == true | soft | sightline |
| Door swing clear | `keep_clear(door.swept)` → sink == true | hard | articulated bake |

---

## 10. Subsystem E — The Validation Cortex

### 10.1 MCP tools (atomic, composable)

| Tool | Purpose | Backend |
|---|---|---|
| `sync_scene(selector)` | Pull relevant actors as proxies into the world model | UE5 adapter |
| `bake_asset(asset_id)` | Run/refresh the Physical Asset Profile | Bake pipeline |
| `get_profile(asset_id)` | Read PAP (+ overrides) | Asset DB |
| `check_collision(a, b?)` | Exact clearance / penetration depth | hpp-fcl (Coal), GJK/EPA |
| `simulate_drop(obj, t)` | Gravity/stability; settled transform + margin | MuJoCo |
| `path_clear(start, goal, r)` | Reachability after a change | RecastNavigation |
| `evaluate_constraints(obj?)` | Run the compiled constraint graph | Constraint engine |
| `validate_operation(diff)` | Orchestrate all checks on a proposed change; structured verdict | orchestrator |
| `suggest_transform(obj, intent)` | Nearest valid transform (repair) | scipy.optimize SLSQP / differentiable objective |
| `commit(diff)` | Dispatch validated diff to UE5 | UE5 adapter |

### 10.2 The gates (with pass/fail visualisation)
A proposed change (`diff`) flows left-to-right through the **Gate Stack** like airport security and halts at the first hard failure. Shared visual grammar: a pill (grey idle / green pass / amber soft-warn / red hard-fail), a headline number, a click-to-expand drawer with the fix vector, and matching evidence painted in the viewport; on a Constraints fail the offending node glows red in the graph; every attempt logs a scrubable timeline frame.

1. **Collision** (`hpp-fcl`/Coal, GJK+EPA) — exact penetration or clearance. *Fail:* objects flash red, overlap shaded, depth callout, separation-normal arrow.
2. **Stability** (MuJoCo) — CoM over support polygon + small perturbation; reports a **margin**, not a bare boolean (drop-sims are parameter-sensitive). *Fail:* CoM dot outside polygon, ghost-topple animation, "shift toward centre" arrow.
3. **Constraints** (compiled graph) — hard sinks gate, soft sinks accumulate into the repair objective. *Fail:* failing sink glows; angle-arc / dimension cue in viewport.
4. **Reachability** (RecastNavigation) — navigability after the change for agent radius r (navmesh pre-baked per scene). *Fail:* pinch point flashes, blocked corridor greys out, "62cm < 90cm".
5. **Commit** (UE5 adapter) — not a gate but the finale; concurrency-guarded; the object appears upright & correct in the photoreal engine.

### 10.3 The agent loop
`sync → propose diff → validate_operation → if fail, read structured diagnostics (which check, exact number, gradient) → suggest_transform or re-reason → re-validate → commit`. `validate_operation` never returns a bare "no" — it returns *why* and *which way to move* — so the agent converges in a couple of steps. That is the token/latency win the architecture exists to deliver.

---

## 11. Subsystem F — Observability

Two live surfaces, both purpose-built for trust and demo:

**Rerun.io — the 3D conscience.** Stream the shadow state every step: proxy meshes (`Mesh3D`), bounding boxes (`Boxes3D`) coloured by validation status, raycasts/sightlines (`LineStrips3D`), the gravity vector, CoM markers, and **ghost overlays** of rejected candidate placements vs. the accepted one. Timeline scrubbing finds the exact step reasoning went wrong; the force-directed graph view renders the scene hierarchy so orphaned/cyclic parenting is obvious before it breaks physics. Use Rerun's explicit `ViewCoordinates` to visually catch any handedness/winding flips.

**The node editor — the intent conscience.** During validation the same constraint graph animates: edges carry live values; constraint sinks glow green/amber/red; a failing node shows its violation magnitude and suggested correction. Optional: a constraint-satisfaction heatmap projected on the floor, and a timeline of constraint scores across attempts.

---

## 12. The World Language (`.wdf`)

Everything above compiles into a single declarative **`.wdf`** file — a portable *language* for physically-grounded, intent-aware worlds. glTF/USD describe geometry; `.wdf` describes **meaning, physics, and intent**.

### 12.1 The grammar — parts of speech

| Part of speech | In PLUMB | Example |
|---|---|---|
| **Nouns** | Assets — baked Physical Asset Profiles | `bronze_figure`, `glass_vase` |
| **Adjectives** | States & materials — how a thing can be | `upright`, `fell`, `hollow`, `autumn` |
| **Verbs** | Affordances — what can be done with it | `sit`, `tap`, `contain`, `illuminate` |
| **Prepositions** | Spatial relations | `on`, `in`, `against`, `near` |
| **Laws** | Constraints — what must hold true | `com_over_base`, `arc_clear` |
| **Grammar** | Bake Profiles — archetype conjugation rules | `profile: articulated` |
| **Tense / mood** | Environment fields — context that modulates all | `season`, `time`, `weather` |
| **Sentences** | Scenes — instances composed under laws | `scene { … }` |
| **Dictionary** | Vocabularies — importable asset+profile packs | `import "gallery.vocab"` |

### 12.2 A single `.wdf` file — vocabulary + sentence

```
# the_gallery.wdf  —  one portable, diffable, validatable document
import "physx.materials"          # shared dictionaries
import "gallery.vocab"

vocabulary {
  asset bronze_figure {
    profile: rigid_prop
    material: { body: bronze }            # → mass 48kg, com high+fwd
    states: [ upright, fell, buried⚙ ]
    affordances: [ base_contact ]
  }
  asset glass_vase {
    material: { shell: glass, interior: hollow }
    states: [ upright, fell ]
    tags: [ fragile ]   load_cap: 0.5kg
  }
  asset oak_door {
    profile: articulated
    joint: { axis: hinge, range: 0..95° }
    swept_volume: keep_clear
  }
}

scene "the_gallery" {
  field season: autumn · time: dusk        # tense / mood

  place bronze_figure on pedestal state upright
  place oak_door at north_wall

  law stable:           com_over_base(margin >= 2cm)      hard
  law facing:           bronze.front -> entrance(<= 8°)   soft
  law no_fragile_load:  byTag(fragile).load <= cap        hard
  law door_clear:       keep_clear(oak_door.swept)        hard
  law walkway:          path_clear(r = 0.45m)             hard
}
```

### 12.3 How a runtime reads it
1. **Vocabulary** — baked, typed, rule-bearing assets, composed from imported dictionaries + local definitions; reusable across worlds.
2. **Sentence** — the scene: instances placed in states, under laws, inside environment fields; this is the "meaning."
3. **PLUMB runtime** — validates the sentence against the laws through the gates; returns the verdict (numbers + fixes) before anything renders.
4. **Engine adapter** — only a valid sentence is realised into UE5 / Unity / Omniverse; the engine is a dumb renderer of pre-verified truth.

### 12.4 Why this is the winning frame
A `.wdf` file is **portable** (any runtime), **diffable** (it's text), **composable** (import vocabularies like libraries), and **validatable** (laws are checkable before render). It turns PLUMB from an app into a **standard** — the "USD for meaning, physics, and intent." That is the artifact a judge remembers and a company could build on.

---

## 13. Data Contracts

**Diff** (agent proposal): `{ "object": "bronze_figure_03", "transform": { "pos": [...], "quat": [...] } }`

**Verdict** (the gate stack as data; the entire UI renders from this):
```json
{ "ok": false, "stopped_at": "stability",
  "gates": [
    { "gate": "collision",   "ok": true,  "clearance_m": 0.042 },
    { "gate": "stability",   "ok": false, "margin_m": -0.07, "fix": { "translate": [0.06,0,0] }, "viz": "com_outside_polygon" },
    { "gate": "constraints", "skipped": true },
    { "gate": "reach",       "skipped": true } ],
  "soft_cost": 1.84 }
```

The **PAP** (§5.5) and the **`.wdf` file** (§12.2) are the other two contracts. PAP is the machine record per asset; `.wdf` is the human-facing language; the verdict is what the gates emit.

---

## 14. Use Cases & Flows

Five audiences, identical gate stack and identical `.wdf` language — the substrate doesn't care what the laws *mean*.

- **A — Set dressing (games, the demo).** "Arrange a museum display, bronze as centrepiece." Intent-driven dressing guaranteed stable, clip-free, door-clear.
- **B — Engineering / load layout.** "Mount these brackets so each carries its load and nothing overheats." PLUMB is a correctness check on AI-generated layouts; structural-bake confidence bands keep claims honest.
- **C — Artistic composition.** "Focal object on the left third, facing the key light." Aesthetic intent as laws — the differentiator vs. physics-only systems.
- **D — Dense robotics scenes (the PhyScensis regime).** "Fill this shelf tightly, all stable." Mass-produce *valid* training scenes; cite PhyScensis as proof the loop works while showing PLUMB makes it reusable + observable.
- **E — Accessibility audit.** "Is this wheelchair-accessible? Fix what isn't." The Reach gate becomes a compliance tool with a visible pass/fail and auto-fix.

---

## 15. The Flagship Demo (~4 minutes)

A real UE5 Gallery scene. Gate Stack visible, constraint graph wired, agent console ready, Rerun timeline empty.

1. **0:00 — frame.** Vanilla LLM attempt: figure floating, clipping the vase, blocking the door. "LLMs place by vibes."
2. **0:30 — understand.** Click the figure → Inspector; point at the baked off-centre CoM and bronze material. "It knows it's top-heavy."
3. **1:00 — intent.** Pan the node graph: face, golden ratio, stable, walkway, door-clear.
4. **1:30 — run.** Prompt "arrange the display." Tool calls stream; the token enters the gate stack.
5. **2:00 — THE MOMENT.** Stability turns red `−7cm`. CoM pops outside the polygon; the figure ghost-topples; arrow says "+6cm toward centre." Facing flags amber `Δ23°`.
6. **2:30 — repair.** `suggest_transform` nudges +6cm, rotates 23°; re-run → all green.
7. **3:00 — commit.** Figure snaps upright & facing into the photoreal shot; door arc clear; navmesh intact.
8. **3:30 — kicker.** Either drag a "fragile" tag onto the vase (a leaning book now fails; agent re-plans) **or** export the `.wdf` file — "everything you saw, in one portable document."

**Demo safety (faked on purpose):** UE5 runs **commit-once**, not a live two-way loop (avoids drift/latency on stage); all reasoning is in canonical space + Rerun, UE5 is the finale render. Assets are **pre-baked** (live-bake one small asset only). Keep a **recorded Rerun session** as fallback if inference stalls.

---

## 16. Competitive Landscape

The space is crowded but fragmented; no system unifies asset-level physical profiling + a user-authorable visual constraint graph + a physics/collision validation API + observability against a production engine. That integration is the whitespace.

| System (year) | Core technique | Steal | PLUMB differs by |
|---|---|---|---|
| **PhyScensis** (OpenReview 2025; UMass/MIT/Genesis AI/MIT-IBM, incl. Tenenbaum, Gan) | LLM proposes physical predicates (contact/support/balance/containment) → physics-engine solver realises → feedback refines; probabilistic programming for stability/controllability | the predicate taxonomy as the starting vocabulary for physical-operator nodes; the closed feedback loop | baked PAP, type-aware profiles, visual node editor, MCP API, `.wdf` file, UE5 target |
| **LayoutVLM** (CVPR 2025) | VLM emits two reinforcing reps + per-constraint **differentiable cost** optimised jointly; relative rotations | differentiable cost-per-constraint; relative-frame rotations (helps handedness) | repair is one of many MCP tools; provenance + observability |
| **ReKep** (CoRL 2024) | constraints = Python keypoint→cost functions, hierarchical real-time solve | "constraint = differentiable cost" representation | visual authoring front-end instead of code-only |
| **VoxPoser** (CoRL 2023) | LLM-composed 3D value maps + planner | value-map abstraction for soft constraints | asset-level profiles; engine integration |
| **Holodeck / LayoutGPT** (CVPR 2024 / 2023) | LLM relational constraints + solver beats direct-coordinate LLM; human-preferred | the thesis itself + human-eval framing (anchor the pitch with this) | reusable substrate + language, not a closed pipeline |
| **Infinigen Indoors** (CVPR 2024) | constraint **DSL** + hierarchical simulated-annealing solver; UE/Omniverse export; strongly preferred in human study | hierarchical solve order; DSL constraint categories (the `.wdf` laws echo this) | user-authorable visual graph; per-asset baked physics |
| **MesaTask** (NeurIPS 2025) | Spatial Reasoning Chain → scene graph + DPO; physics-verified dataset | scene-graph IR; physics-verification as eval signal | live validation oracle + observability |
| **Mind's Eye** (2022, Google/DeepMind) | inject MuJoCo outcomes into the prompt; large zero/few-shot accuracy gains | the citation justifying the `simulate_drop` oracle | sim is a callable MCP tool with a structured verdict |
| **PhysX-Anything / PhysXNet** (2025–26, NTU/Shanghai AI Lab) | VLM single-image → sim-ready URDF/XML; 5-dimension physics schema (scale/material/affordance/kinematics/function) | use as the bake back-end + adopt the 5-dim schema; URDF/XML export feeds MuJoCo | caches result as overridable, locked, provenance-tracked PAP |
| **3D-MCP (Plask) / blender-mcp / UE-MCP** | MCP CRUD/automation bridges to DCCs (entity-first, atomic vs compound) | entity-first schema; atomic vs compound tool split | adds physics validation, baking, constraint solving, a language |

---

## 17. Technical Risks & Mitigations (ranked by likelihood × demo impact)

1. **UE5 live bridge — #1 silent-failure risk (high × high).** Running a Python server inside Unreal can crash the editor; the Remote Control HTTP API is slow for batch ops; UE 5.5 renamed Python object paths, breaking calls; Python is editor-only. **Mitigation:** episode-scoped snapshot → reason in canonical space → single commit; optimistic-concurrency hash; **Three.js fallback viewer** on the same schema so a UE5 hiccup can't sink the demo. If round-trip > ~1–2s or any coordinate round-trip test fails, do not demo live UE5 — show commit only as the finale.
2. **V-HACD is deprecated (high × medium).** Its author moved to CoACD; V-HACD fills holes/slots, corrupting collision + affordance baking. **Mitigation:** use **CoACD** (optionally VisACD for GPU speed).
3. **Single-mesh mass/material/stiffness inference is the weakest scientific claim (high × medium).** NeRF2Physics' best mass error is large (ADE ~8.7 kg on ABO-500) and interior is unknowable from surface alone; PhysX-Anything attributes are *plausible, not measured*; Young's-modulus from geometry has no credible single-asset SOTA. **Mitigation:** label structural outputs as priors with confidence; never hard-gate on them; surface uncertainty in the PAP; allow manual override (a feature, not a workaround).
4. **MuJoCo as a validity oracle is parameter-sensitive, not deterministic-by-default (medium × high).** Soft penalty-based contacts; `solref`/`solimp`, timestep, and friction affect outcomes; a single drop-sim's "settled = stable" can flip. **Mitigation:** gate on a **quasi-static test (CoM-over-support-polygon + small perturbation)** and report a *margin*, not a boolean.
5. **Coordinate normalisation — classic silent killer (medium × high).** Handedness flip, winding-order, cm↔m produce mirror geometry, inverted normals, 100× offsets that *look* plausible until physics runs. **Mitigation:** one unit-tested boundary adapter with golden round-trip tests (UE5→canonical→UE5 = identity) + Rerun `ViewCoordinates`.
6. **scipy SLSQP local minima / scaling on dense scenes (medium × medium).** SMT/Z3 layout is exact but blows up combinatorially; unsuited to continuous real-time geometry. **Mitigation:** tier the solver — SLSQP (small local repairs) → differentiable batched objective (dense scenes, LayoutVLM-style, optionally MJX/Warp/Genesis) → SMT/Z3 (discrete constraints only: counts, ordering). **Caveat:** contact gradients through differentiable physics are often wrong/zero through contact events — use differentiable physics for *non-contact* spatial costs and keep contact-stability as a *forward* check.
7. **RecastNavigation parameter sensitivity (low × medium).** Cell size, agent radius/height, slope mis-sets silently drop thin passages. **Mitigation:** pre-tune params per demo scene; avoid live re-baking arbitrary geometry.
8. **hpp-fcl → "Coal" name/version churn (low × low).** Renamed in 2024; GJK/EPA reimplementation is fast and returns a distance lower bound — solid, but accuracy is bounded by **decomposition quality** (so the real risk is upstream CoACD, not Coal).

---

## 18. Architecture Optimizations (ranked by wow-per-unit-risk)

1. **V-HACD → CoACD.** Removes a deprecated dependency; fixes the hole-filling that corrupts collision + affordance baking.
2. **Adopt the PhysX five-dimension schema for the PAP and use PhysX-Anything/PhysXNet as the bake back-end.** Turns the riskiest subsystem into a citable, SOTA-backed one; yields URDF/XML export toward the MuJoCo oracle.
3. **Constraint compiler emits differentiable Python cost functions (ReKep/LayoutVLM style), not opaque predicates.** Unifies validation and repair (same cost read for diagnostics and minimised for repair) and produces "violation magnitude + gradient direction" for free.
4. **Tier the solver** (SLSQP → differentiable batched → SMT for discrete), per the §17.6 caveat.
5. **Episode-scoped, commit-once UE5 sync** with optimistic-concurrency hash — sidesteps drift, latency, version churn.
6. **Use Coal's distance lower-bound as the soft-collision signal**, feeding the same objective as the constraint costs.
7. **Lean into Rerun as the demo centrepiece** — it natively supports the exact primitives (Points3D, Transform3D, ViewCoordinates, timeline, side-by-side blueprints) and is built for spatial/embodied AI; lowest-risk, highest-impact.

**Over-engineered / silent-fail-prone for a live demo:** the structural bake (keep as a labeled "experimental prior" panel); continuous two-way UE5 sync (collapse to commit-once); live RecastNav re-baking (pre-bake per scene).

---

## 19. Novelty & Positioning

**Honest assessment:** PLUMB is *not* novel as "LLM + physics + constraint solving for layout" (PhyScensis, LayoutVLM, Holodeck, Infinigen) nor as "MCP for a DCC" (blender-mcp, UE servers, 3D-MCP). Expect a knowledgeable judge to know PhyScensis — name it first.

**Where the defensible contribution actually lies:**
1. The **Physical Asset Profile as a cached, user-overridable, provenance-tracked, lockable, type-aware sidecar** — turning expensive per-asset physical understanding into a *reusable artifact*; everyone else recomputes per scene.
2. **Exposing the validation oracle as composable, atomic MCP tools** that return *structured, numeric, gradient-bearing verdicts* — making physical reasoning a first-class agent capability.
3. The **visual constraint + behaviour authoring surfaces** (node editor + Asset Studio) over what are otherwise code-only constraint systems.
4. The **`.wdf` language** — a portable, composable, validatable description of meaning/physics/intent, i.e. "USD for semantics."

**Pitch frame:** "Holodeck and PhyScensis prove LLMs need a physics-grounded solver to place objects plausibly — but those are closed research pipelines. PLUMB is the *reusable substrate and language*: type-aware baked asset physics, a visual constraint/behaviour authoring layer, a physics-validation API any agent can call, full observability, and a portable `.wdf` file. We make 'is this physically valid, and exactly how do I fix it?' a tool call — and 'an entire physically-grounded world' a single document."

---

## 20. Build Roadmap

Each milestone is independently demoable; submit the latest reached *cleanly*, not the most code.

- **M1 — Canonical core (no UE5).** PAP schema; geometric bake (CoACD); `check_collision` (Coal); Gate Stack UI rendering from the verdict JSON; Rerun wired. *Demoable:* token hits a red Collision gate with ghost + callout.
- **M2 — Physics truth** *(already a winning demo).* Composition-aware physical bake; `simulate_drop`/quasi-static Stability gate with CoM-over-polygon viz. *Demoable:* the topple-and-repair beat end to end.
- **M3 — Intent + Studio.** Constraint node editor + compiler + live graph; Asset Studio rest-state authoring + fill/socket regions. *Demoable:* facing amber → repair → green; drag-a-tag re-reason.
- **M4 — Profiles + Engine.** Bake Profiles with three archetypes (door / tree / shelf); UE5 commit-once adapter (handedness/scale/winding + golden round-trip tests + concurrency guard). *Demoable:* the door swing keep-clear; photoreal commit finale.
- **M5 — The Language + breadth.** Serialise/deserialise the `.wdf` file (round-trip a scene); Reachability gate; differentiable repair for dense scenes; burial regression; the five use-case presets.

---

## 21. Tech Stack

| Layer | Choice | Notes |
|---|---|---|
| MCP server | **FastMCP** (Python 3.12+) | atomic tools; stateless per query; caches world model in memory |
| Geometry | **trimesh** | scene graph, OBB/AABB, volume, raycasts, relations |
| Convex decomposition | **CoACD** (opt. VisACD) | collision-aware; replaces deprecated V-HACD |
| Collision / clearance | **hpp-fcl (Coal)** | GJK + EPA, exact distance lower-bound, safety margins |
| Physics / stability | **MuJoCo** | gravity, drop test, contact settling; gate on quasi-static margin |
| Pathfinding | **RecastNavigation** (pynavmesh / pyrecastdetour) | navmesh reachability; pre-tuned per scene |
| Repair solver | **scipy.optimize SLSQP** → differentiable objective (MJX/Warp/Genesis) → Z3 for discrete | tiered; avoid Z3 for continuous geometry |
| Semantic / composition bake | **VLM (render-and-ask)** or PhysX-Anything/PhysXNet; PointNet-class fallback | adopt PhysX 5-dim schema; cache aggressively |
| World model / schema | bespoke JSON, Z-up RH metres | one rigid canonical convention |
| UE5 transport | **C++ Automation Bridge** (reuse Hayba) | only place that knows UE5's LH / Z-up / cm |
| Node editor UI | **React + React-Flow / Rete.js** (reuse Falcentry) | authors + visualises constraints; typed ports |
| Observability | **Rerun.io** | viewport, timeline, force-directed scene graph, ViewCoordinates |
| Language | bespoke `.wdf` (text) + serializer | vocabulary + sentence; imports; validatable |

---

## 22. Appendix

### Glossary
- **PAP — Physical Asset Profile.** The baked, cached, overridable record of what an asset is.
- **Bake Profile.** A type-specific recipe (passes + default states/sockets/constraints) loaded by archetype detection.
- **Rest State.** A named, demonstrated pose defining how an object contacts a surface (upright / fell / leaning / buried).
- **Region.** A painted zone on an asset with a typed rule (fill / socket / contact / keep-clear).
- **Gate.** A validation stage returning pass/fail + number + gradient (Collision / Stability / Constraints / Reach).
- **Verdict.** The structured JSON the gate stack emits; the UI renders from it.
- **`.wdf` file.** The portable language document: vocabulary (assets + profiles) + sentence (scene + laws + fields).
- **Soft / hard constraint.** Soft → weighted repair objective; hard → gates the commit.

### Pitch lines (memorise)
- *One sentence:* "glTF and USD describe geometry; PLUMB describes meaning, physics, and intent."
- *The mechanism:* "Every gate is a cost function, so the thing that rejects a placement is the thing that fixes it."
- *The moat:* "Bake once into a type-aware, provenance-tracked profile; validate every move; compile it all into one portable `.wdf` file."
- *The honest novelty:* "Not a new idea in research — a new *substrate and language* that makes the idea reusable."
