# PLUMB — Decision Record (the grill outcomes)

Resolved during the design grill. This is the canonical "why" behind the code.
Every row says **what we decided**, **why**, and **who owns building it**.

**Owners:** **zajalist = Cortex (Person A)** · **FaraDuMatin = Conscience (Person B)**

> Cortex (A) *produces* Verdicts (headless physics/logic). Conscience (B) *drives the
> agent + renders* Verdicts, and owns the language + the UE5 bridge. They meet only at
> [`contracts.py`](contracts.py). Frontend is deferred until the logic is done.

---

## The bet
**Topple-and-repair** is the one beat the submission rides on: a top-heavy bronze
figure placed too near a pedestal edge → Stability gate red `−7cm` → CoM pops outside
the support polygon → ghost-topple → `suggest_transform` nudges it → re-run all green →
snaps upright. Everything else is a bonus ring layered on the same Verdict JSON.

---

## Decisions

| # | Decision | What we chose | Why | Owner |
|---|---|---|---|---|
| Q1 | Scale | 2 people · one weekend · heavy codegen | Bottleneck is integration, not typing | both |
| Q2 | Demo bet | Topple-and-repair, rendered in Rerun | Visceral, self-contained, no UE5 needed to land | both |
| Q3 | The seam | Split on the **Verdict JSON**; A produces, B renders/drives | Lets each code against fixtures, never blocked | both |
| Q4 | Stability gate | **Quasi-static CoM-over-support-polygon margin** (the "string trick"); MuJoCo only animates the ghost-topple, never judges | Deterministic, testable, *is* the cost function & the viz; MuJoCo pass/fail is parameter-flaky (§17.4) | **A** |
| Q5 | Bake fidelity | **Notch 3 — full composition-aware** | The real moat; "it knows it's top-heavy because the bronze is up top" | **A** |
| Q6 | Material assignment | **VLM + texture sampling** guess the material per CoACD part | Real auto-understanding, not hand-typed | **A** (guess) · **B** (confirm UI) |
| Q7 | Confirm loop | Human **confirms before lock**; default **prebaked** (Option B), with a **`live` settings toggle** (Option A) | Trust moment + keeps flaky VLM off the live critical path; same component both modes | **A**+**B** |
| Q8 | Repair scope | `suggest_transform` solves **translate + yaw** | A statue slides & spins, never tumbles | **A** |
| Q9 | Repair solver | **SLSQP** over the live gate cost (stability+collision hard, facing soft), **greedy nudge fallback** if it stalls | "Validation and repair are the same math"; fallback guarantees a fix on stage (§17.6) | **A** |
| Q10 | Agent | **Scripted driver first, real LLM as Sunday upgrade, recorded fallback** (Option C) | Honest thesis available without betting 4 min on live inference; same MCP path either way | **B** |
| Q11 | Collision gate | **Convex-part clearance** from the CoACD parts; `trimesh`/FCL only if it installs clean; skip standalone Coal | Reuses bake output, zero wheel-risk, real number | **A** |
| Q12 | Constraints / node editor | **Hardcoded Python cost functions now; no node editor.** Frontend (incl. read-only status graph) deferred until logic done | Beat needs real costs, not an authoring app | **A** (costs) · **B** later (graph) |
| Q13 | `.wdf` language | **Full round-trip**: prove `load(save(scene)) == scene` | It's the "judge remembers it" artifact; do it right | **B** |
| Q14 | UE5 transport | **Remote Control HTTP API** (no C++ compile), commit-once, concurrency-guarded | Fastest real UE5 link; latency irrelevant when episode-scoped & commit-once; C++ plugin is post-hackathon | **B** |
| Q15 | Coordinate adapter | Written from scratch (no Hayba). **Negate-X mirror**, single 4×4 `M`+inverse, quaternion component-flip, **winding re-flip in the adapter**, proven by **golden round-trip tests + Rerun ViewCoordinates** | §17.5 silent killer — only proof makes it right; refuse live UE5 if a golden test fails | **B** |
| Q16 | Reachability gate | **2D floor-projection**: narrowest-gap along walkway + flood-fill connectivity for radius r; no Recast bindings | Correct for room-dressing nav, zero C++ wheel/param risk (§17.7/§18); real Recast is post-hackathon | **A** |
| Q17 | Bake Profiles (moat) | Build the **architecture + 3 archetypes (door/tree/shelf)** per §6.4. Detector = **VLM-suggests / human-confirms** (reuses Q7 UI) with authored `.wdf` `profile:` as override; **joint axis/range authored**, swept-volume = real geometry, **door gate = collision vs. the swept solid** (no new gate) | Moat falls out of the spine; joint *inference* is §17.3 research-grade, so authored | **A** (passes/geometry) · **B** (`.wdf` profile syntax) |

---

## Ownership map (who builds what)

### zajalist — Cortex (`cortex/`) — produces Verdicts
- `world.py` — scene graph `{node_id: (PAP, Transform)}`, canonical Z-up RH metres
- `bake.py` — **CoACD parts → density-weighted mass/CoM/inertia** (Notch 3), hollowness via interior rays
- material guess backend — VLM render-and-ask **+** texture sampling → `MaterialGuess[]`
- `gates/stability.py` — quasi-static CoM-over-polygon **margin** (the bet)
- `gates/collision.py` — convex-part clearance/penetration
- `gates/reach.py` — 2D floor-projection narrowest-gap + flood-fill
- `gates/constraints.py` — hardcoded law cost functions (facing/stable/walkway/door_clear…)
- `repair.py` — `suggest_transform` SLSQP(translate+yaw) + greedy fallback
- `orchestrator.py` — `validate_operation(diff) → Verdict` (gates L→R, halt on hard-fail)
- `bake_profiles/` — detector + door/tree/shelf passes; door swept-volume geometry
- `server.py` — FastMCP exposing `MCP_TOOLS`

### FaraDuMatin — Conscience (`conscience/`) — drives the agent + renders + language + engine
- `agent_loop.py` — scripted driver first → real LLM MCP client (Sunday), recorded fallback
- `wdf/` — **full round-trip** serializer + parser; `load(save(scene)) == scene` test
- `ue5/` — Remote Control HTTP bridge: `sync_scene` (GET tagged actors), `commit` (PUT), snapshot-hash concurrency guard
- `ue5/adapter.py` — negate-X coordinate transform + **golden round-trip tests** (the §17.5 proof)
- `confirm_panel` — renders `MaterialGuess[]`, human approve/edit → lock (prebaked + live modes)
- `rerun_viz.py` — CoM marker, support polygon, gravity vector, ghost-topple, fix arrow, ViewCoordinates
- **(deferred)** frontend: Gate Stack UI + read-only status graph, both rendered from Verdict JSON

### Shared / first thing Friday night (both, together)
- `contracts.py` frozen (done) · `fixtures.py` fake verdicts (done) · CI running the golden coordinate tests

---

## Integration points (the only times you must sync)
1. **Sat night — Integration #1:** B swaps `from fixtures import` → real `validate_operation`/`suggest_transform` calls.
2. **Sun — UE5 commit:** B's adapter passes golden tests → real commit-once into UE5 (else fall back to Rerun-only).
3. **Sun — `.wdf` round-trip:** B serializes the validated world model A produced → proves load/save identity.

## Standing safety rules (from §17/§18 — non-negotiable)
- Structural bake (stiffness/max-load) = **labeled experimental prior, never hard-gated**.
- UE5 = **commit-once**, never live two-way; if round-trip >1–2s or any golden test fails → Rerun-only demo.
- Nothing re-bakes navmesh live; pre-baked per scene.
- Python **3.12** (not 3.14 — physics wheels lag).
