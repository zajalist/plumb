# PLUMB

**A spatial cortex and a language for physically-grounded, intent-aware 3D worlds.**

LLM agents driving 3D worlds are spatially blind — they emit transforms from text
priors and discover failure only after the fact (objects in walls, floating assets,
unstable stacks, blocked doors). PLUMB sits between any agent and a 3D engine and
**validates every proposed change before it commits**, returning not just *no* but
the exact number it failed by and the direction to fix it.

Full vision: [`PLUMB_master_spec.md`](D:/McGill/SummerCourse/PLUMB_master_spec.md).
This repo is the **weekend build** — scoped to the one beat we bet on.

---

## The bet (the one beat that must land)

**Topple-and-repair.** A top-heavy bronze figure is placed too close to a pedestal
edge. The **Stability gate** flashes red `−7cm`, its centre of mass pops outside the
support polygon, the figure ghost-topples, an arrow says *"+6cm toward centre."*
`suggest_transform` nudges it, we re-run, **all green**, and it snaps upright.

Everything else in the spec (UE5 bridge, node editor, `.wdf` language, Asset Studio,
14 archetypes) is a **bonus ring** we add only if the core beat is locked.

Rendered entirely in **Rerun** — no live UE5 in the demo (commit-once screenshot at most).

---

## The seam (how two people never block each other)

Everyone meets at **one frozen contract**: [`contracts.py`](contracts.py) — the
`Diff`, `Verdict`, and `PAP` schemas plus the MCP tool signatures. Until the real
cortex exists, Person B builds against [`fixtures.py`](fixtures.py) (fake verdicts).
Same JSON shape either way.

```
        Diff ──▶  [ CORTEX (Person A) ]  ──▶  Verdict  ──▶  [ CONSCIENCE (Person B) ]
                  produces truth                            renders truth + drives agent
                        │                                            │
                        └──────────────  contracts.py  ─────────────┘   (the only shared surface)
```

### zajalist — `cortex/` — *produces Verdicts* (Person A)
Headless, deterministic, unit-testable. Composition-aware bake (CoACD parts →
density-weighted mass/CoM/inertia) → world model → gates (Stability = quasi-static
CoM-over-polygon margin, Collision = convex-part clearance, Reach = 2D floor projection,
Constraints = hardcoded cost functions) → `suggest_transform` repair (SLSQP translate+yaw
+ greedy fallback) → bake profiles (door/tree/shelf) → FastMCP tool surface.
**Done when:** `validate_operation(topple_diff)` returns a stability-fail Verdict and
`suggest_transform` flips it green.

### FaraDuMatin — `conscience/` — *drives the agent + renders + language + engine* (Person B)
Agent loop (scripted → real LLM, recorded fallback), the `.wdf` **full round-trip**
serializer/parser, the **UE5 Remote Control bridge** + negate-X coordinate adapter with
golden round-trip tests, the material-confirm panel, and Rerun viz (ghost-topple, CoM
marker, support polygon, fix arrow). Frontend (Gate Stack UI + status graph) deferred
until the logic is done.
**Done when:** feeding `VERDICT_TOPPLE` then `VERDICT_REPAIRED` shows red→green; `.wdf`
round-trips; UE5 commit-once lands (or falls back to Rerun).

> Person B is **never blocked**: code against `fixtures.py`, swap to real MCP calls last.

Full decision record + per-file ownership: [`DECISIONS.md`](DECISIONS.md).

---

## Day plan (one weekend, two people, heavy codegen)

| When | zajalist — cortex (A) | FaraDuMatin — conscience (B) |
|---|---|---|
| **Fri night** | freeze `contracts.py` together · `world.py` + load a real mesh | freeze contracts together · Rerun draws a box + CoM from `fixtures` |
| **Sat AM** | `bake.py`: CoACD parts + mass/CoM/inertia → real PAP | `gate_stack.py`: pill row + drawer from any Verdict |
| **Sat PM** | Stability gate (CoM-over-polygon + perturbation) → real Verdict | ghost-topple + fix-arrow viz; agent loop against fixtures |
| **Sat night** | **integration #1**: B calls A's `validate_operation` for real | same |
| **Sun AM** | `suggest_transform` (SLSQP) flips topple → green | wire repair into the loop; record the 4-min beat |
| **Sun PM** | Collision gate + FastMCP polish (bonus rings) | `.wdf` export reveal / node-graph stretch (bonus) |
| **Sun eve** | freeze, rehearse, keep a recorded Rerun fallback | freeze, rehearse |

Submit the **latest clean milestone**, not the most code.

---

## Setup

> **Python 3.12** (not 3.14 — physics wheels lag). Use a 3.12 venv.

```bash
python3.12 -m venv .venv
. .venv/Scripts/activate        # PowerShell: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

## Layout

```
contracts.py     # FROZEN. Diff / Verdict / PAP / MCP tool signatures. The seam.
fixtures.py      # Fake verdicts + PAPs so Person B starts unblocked.
cortex/          # Person A — produces Verdicts (headless).
conscience/      # Person B — renders Verdicts + drives the agent.
PLUMB_master_spec.md  # the full vision (reference, not the weekend scope).
```
