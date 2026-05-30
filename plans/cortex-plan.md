# Cortex Implementation Plan (zajalist / Person A)

Headless physics/logic that **produces Verdicts**. Every task is TDD, commits on
green, and depends only on `contracts.py` + earlier tasks — never on `conscience/`.

**Canonical space everywhere:** Z-up, right-handed, metres, kilograms.
**Spine toward the bet (topple-and-repair):** Tasks 1 → 2 → 3 → 4 → 8 → 9.
Tasks 5,6,7,10,11 are rings on the same Verdict.

**Dependency note:** CoACD may not have a Python 3.12/Windows wheel. Geometry bake
MUST degrade gracefully: try `coacd`; if unavailable, fall back to
`trimesh.decomposition`/`convex_hull` and set a `decomposition: "coacd"|"fallback"`
flag so we never silently ship worse parts.

---

## Task 1 — `cortex/world.py`: the world model

**Spec.** A `WorldModel` holding `{node_id: WorldNode}` where `WorldNode` = `{pap: PAP,
transform: Transform, parent: str|None}`. Methods: `add(node_id, pap, transform,
parent=None)`, `get(node_id) -> WorldNode`, `update_transform(node_id, transform)`,
`remove(node_id)`, `nodes() -> list[node_id]`, and `snapshot_hash() -> str` (stable
sha256 over sorted node ids + rounded transforms + pap.asset_id+bake_version — this is
the optimistic-concurrency guard for `commit`). No physics here, pure state.

**Tests.** add/get round-trips; update changes the hash; identical states hash equal;
reordering insertions hashes equal; removing is reflected. ≥6 tests.

**Done when:** all tests green, committed.

---

## Task 2 — `cortex/bake/geometry.py`: geometric bake

**Spec.** `bake_geometry(mesh_path) -> Geometry` using `trimesh`: load mesh, compute
AABB + OBB half-extents, `volume_m3`, `watertight`, and convex parts via CoACD (with the
graceful fallback above). Return the `Geometry` contract object plus the raw convex part
meshes (kept in an internal structure the physical bake + collision will consume — expose
a `bake_geometry_parts(mesh_path) -> (Geometry, list[trimesh.Trimesh])`).

**Tests.** On a unit cube mesh fixture (generate via `trimesh.creation.box`): volume ≈ 1.0,
watertight True, ≥1 convex part, OBB half-extents ≈ [0.5,0.5,0.5]. On a non-watertight
fixture, `watertight` False. Decomposition flag present. ≥5 tests. (Use `trimesh.creation`
primitives as fixtures — no external asset downloads in tests.)

**Done when:** green + committed. If CoACD import fails in the env, the fallback path is
the one exercised and a test asserts the flag == "fallback".

---

## Task 3 — `cortex/bake/physical.py` + `cortex/bake/__init__.py:bake_asset`

**Spec.** A material→density table (`MATERIAL_DENSITY = {"bronze":8800,"stone":2500,
"glass":2500,"wood":700,"default":1000}` kg/m³). `bake_physical(parts, part_materials) ->
Physical`: for each convex part compute its volume + centroid, assign density from its
material (parts default to "default"), then **mass = Σ ρ·V**, **CoM = Σ(ρ·V·centroid)/mass**
(density-weighted, NOT uniform centroid), and the **3×3 inertia tensor** about the CoM
(sum part inertias via parallel-axis). Hollowness via interior ray test
(`trimesh.ray`): sample points, if interior rays mostly miss solid → `hollow=True`.
Then `bake_asset(asset_id, mesh_path, part_materials=None, profile="rigid_prop") -> PAP`
composes geometry (T2) + physical into a full `PAP`, with `provenance.locked` listing any
fields fed from authored `part_materials`.

**Tests.** Two-part fixture: a heavy small box stacked on a light big box with bronze-on-top
materials → assert CoM_z sits **above** the uniform-density centroid (the "top-heavy"
property — the whole moat). Uniform single material → CoM ≈ geometric centroid. Inertia
tensor symmetric, positive diagonal. Hollow shell fixture → `hollow True`. Mass of unit
bronze cube ≈ 8800 kg. ≥6 tests.

**Done when:** green + committed. This is the headline bake — the CoM-above-centroid test
is the proof the composition math is real.

---

## Task 4 — `cortex/gates/stability.py`: the Stability gate (THE BET)

**Spec.** `support_polygon(pap, transform) -> list[2D pts]`: project the asset's
ground-contact footprint (use `structural.support_footprint` if present, else the lowest
convex-part hull projected to the floor) into world XY at the given transform. `stability(pap,
transform) -> GateResult`: project world CoM straight down (plumb line) to XY; signed margin
= distance from projected CoM to the support polygon boundary (**+inside, −outside**) via
point-in-polygon + nearest-edge distance. `ok = margin >= STABILITY_MARGIN_M` (default 0.02).
On fail, `fix.translate` = horizontal vector from projected CoM toward the polygon centroid
scaled to restore margin; `viz="com_outside_polygon"`; `detail` like "CoM 7cm outside polygon".
Pure `numpy` (+ `shapely` if you want robust polygon ops). Deterministic.

**Tests.** Centered CoM over a square base → margin > 0, ok True. CoM shoved past an edge →
margin < 0, ok False, fix points back toward centre, applying fix flips it to ok. Margin sign
and magnitude match hand-computed values on a unit square. The bronze-figure fixture from T3
placed at a pedestal edge reproduces a **negative margin near −0.07** (the demo number, within
tolerance). ≥7 tests.

**Done when:** green + committed. `stability()` is also a pure cost function (the margin) —
keep it callable by the repair solver (T8).

---

## Task 5 — `cortex/gates/collision.py`: the Collision gate

**Spec.** `collision(world, a, b=None) -> GateResult` using convex-part clearance: between
node `a`'s parts and node `b`'s parts (or all other nodes if `b` None), compute min distance
(positive = clearance) or penetration depth (negative) via convex-hull GJK-style distance.
Use `trimesh`'s collision manager / FCL if it imports cleanly; else a convex separating-axis
distance over the parts. `value_m` = signed clearance; `ok = value_m >= 0`; on penetration,
`fix.translate` = separation along the contact normal.

**Tests.** Two boxes apart → positive clearance, ok. Overlapping → negative, ok False, fix
separates them. Touching → ≈0. ≥5 tests.

**Done when:** green + committed.

---

## Task 6 — `cortex/gates/reach.py`: the Reachability gate (2D)

**Spec.** `reach(world, walkway_poly, agent_r=0.45, start=None, goal=None) -> GateResult`:
project all obstacles to the floor; compute the narrowest free-gap width along the walkway
polygon; `value_m` = that width; `ok = width >= 2*agent_r`. Also a flood-fill on a coarse
floor grid to confirm `goal` reachable from `start` after obstacles. `detail` like
"walkway 94cm >= 90cm". Pure numpy/shapely, no Recast.

**Tests.** Empty walkway → full width, ok. Obstacle pinching to 0.6m with r=0.45 (diameter
0.9) → ok False, "62cm < 90cm"-style detail. Flood-fill: obstacle fully blocking → goal
unreachable. ≥5 tests.

**Done when:** green + committed.

---

## Task 7 — `cortex/gates/constraints.py`: hardcoded laws

**Spec.** A registry of law cost functions, each `(world, params) -> ConstraintResult`
(name, ok, hard, magnitude, detail). Implement at least: `facing` (soft — angle between an
object's `front` and the direction to a target ≤ tol; magnitude = degrees over),
`com_over_base` (hard — wraps stability margin), `walkway` (hard — wraps reach), `door_clear`
(hard — collision vs a swept-volume obstacle). `evaluate_constraints(world, laws) ->
GateResult(gate=constraints, constraints=[...])` aggregates; gate ok = all hard laws ok;
soft magnitudes summed into the verdict's `soft_cost`.

**Tests.** facing within tol → ok soft; beyond tol → not ok, magnitude = degrees over,
"Δ23°"-style detail. A hard law failing makes the gate not-ok. Soft failing does not gate.
≥6 tests.

**Done when:** green + committed.

---

## Task 8 — `cortex/repair.py`: `suggest_transform` (the "repair")

**Spec.** `suggest_transform(world, obj, intent) -> Transform`. Build an objective over
decision vars **[dx, dy, dyaw]** (translate + yaw only): hard constraints = stability margin
≥ tol and collision clearance ≥ 0 (as scipy inequality constraints); soft objective = facing
magnitude + small movement penalty (stay near original). Solve with
`scipy.optimize.minimize(method="SLSQP")`. If it fails to converge or violates a hard
constraint, **greedy fallback**: apply the stability gate's own `fix.translate` directly.
Return the resulting full `Transform`. Reuses the gate functions from T4/T5/T7 as the cost —
do NOT re-derive the math.

**Tests.** Topple fixture (bronze at pedestal edge) → returned transform makes
`stability().ok` True. A case where sliding would collide → SLSQP finds a yaw/translate that
satisfies both, or greedy fallback still returns a stability-valid transform. Returned
transform is a valid `Transform`. ≥5 tests.

**Done when:** green + committed. With T4 this completes topple-AND-repair.

---

## Task 9 — `cortex/orchestrator.py`: `validate_operation`

**Spec.** `validate_operation(world, diff, laws=None) -> Verdict`: apply the diff to a copy
of the world, run gates **left→right: collision → stability → constraints → reach**, halting
at the first **hard** failure (later gates `skipped=True`). Populate `stopped_at`, each
`GateResult`, and `soft_cost`. `ok = no hard failure`. Must reproduce the shape of
`fixtures.VERDICT_TOPPLE` (collision ok, stability fail, constraints+reach skipped) for the
topple input, and `VERDICT_REPAIRED` shape after applying `suggest_transform`.

**Tests.** Topple diff → Verdict matches VERDICT_TOPPLE shape (stopped_at=stability, later
skipped). After repair → ok True, nothing skipped. Collision hard-fail halts before
stability. ≥5 tests.

**Done when:** green + committed. This is the cortex's public contract output.

---

## Task 10 — `cortex/server.py`: FastMCP surface

**Spec.** Expose every tool in `contracts.MCP_TOOLS` over FastMCP (stdio), delegating to
the modules above. `validate_operation`, `suggest_transform`, `bake_asset`, `get_profile`,
`check_collision`, `simulate_drop` (→ stability), `path_clear` (→ reach),
`evaluate_constraints`, `sync_scene`/`commit` (stubs that B's UE5 bridge fills). Returns
contract objects as JSON.

**Tests.** Tool registry matches `MCP_TOOLS` keys; calling `validate_operation` over the
server on the topple fixture returns the expected verdict JSON. ≥3 tests (in-process client).

**Done when:** green + committed.

---

## Task 11 — `cortex/bake_profiles/`: door/tree/shelf (the moat)

**Spec.** `Profile` = `{detect(pap)->bool, passes(pap)->pap, default_states, default_regions,
default_constraints}`. Registry + `load_profile(pap)` (authored `pap.profile` wins; else
VLM/heuristic detect). **Door (articulated):** authored `joint{axis,range}` →
`swept_volume(pap, transform) -> mesh` = union of door-hull poses rotated 0→range about the
hinge axis; expose it as a static obstacle so `door_clear` (T7) = collision vs the sweep.
**Tree:** seasonal state set + attach-band region stub. **Shelf:** fill-region capacity +
`populate(region, assets)` that emits placements each re-validated through T9.

**Tests.** Door sweep of a 95° hinge produces a wedge whose volume > the door panel volume;
a box placed inside the wedge fails `door_clear`, outside passes. Profile detection picks
articulated for authored `profile: articulated`. Shelf `populate` yields only gate-valid
placements. ≥6 tests.

**Done when:** green + committed.

---

## After all tasks
Final whole-cortex review, then `superpowers:finishing-a-development-branch` to merge `cortex`.
