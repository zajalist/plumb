# PLUMB Studio — Parallel Work Handoff

**Date:** 2026-05-30 · **For:** zajalist (dispatcher) to run multiple AI agents at once.

Each **Work Package (WP)** below is a self-contained brief for one agent/session. To
dispatch an agent, give it: **(a)** the "Shared contracts" section, **(b)** the one WP,
**(c)** its own git branch/worktree. Agents must never edit files outside their WP.

---

## Ownership map (so nobody collides)

| Track | Owner | Files |
|---|---|---|
| Backend playground + bake workbench | **this session** (zajalist + Claude) | `studio/server.py`, `studio/src/{api.ts,theme.css,AssetsPanel,Viewport,Properties,GateStack,Inspector}.tsx`, `App.tsx` shell |
| Node editor | **Fara** | `studio/src/ConstraintGraph.tsx` |
| Everything below | **parallel agents you dispatch** | as scoped per WP |

Design + architecture source of truth: `docs/superpowers/specs/2026-05-30-plumb-studio-backend-design.md`.

---

## Shared contracts (EVERY agent must honor)

1. **Data shapes are frozen — `contracts.py`** (`PAP`, `Verdict`, `Diff`, `GateResult`,
   `MaterialGuess`). Never edit it. Frontend mirrors it in `studio/src/verdicts.ts`/`api.ts`.
2. **Design system is owned by this session — `studio/src/theme.css`** (color tokens, the
   Geist/Geist-Mono fonts, the custom SVG icon `<symbol>` sheet, the "no glow / no LED
   dots / no gradient / hairlines-only" rules). Agents **consume** tokens + icons; they do
   **not** redefine colors or invent icons. If you need a new icon, request it (don't
   inline a lucide/emoji — that breaks the brand).
3. **Two different servers — do not confuse them:**
   - `studio/server.py` = **FastAPI HTTP** bridge for the *browser* (request/response).
   - `cortex/server.py` = **FastMCP** surface for *LLM agents* (MCP tools).
4. **Branch discipline:** one WP = one branch off the integration line; PR back; rebase on
   `contracts.py`/`theme.css` changes. Never touch another track's files.
5. **No client-side physics, ever.** All numbers come from a `PAP`/`Verdict` the backend
   produced. The UI only renders.

---

## START NOW — parallel-safe (no shared-file collision)

### WP-1 — Splash / launch screen
- **Goal:** the pre-IDE launch screen: brand moment (the real `plumb.svg` aperture mark),
  then **New .wdf · Open .wdf · Open recent**. Austere, on-brand, fast.
- **Owns:** `studio/src/Splash.tsx`, `studio/src/recent.ts` (recent-files in localStorage).
- **Consumes:** `theme.css` tokens + logo symbol; a `onOpenProject(path)` / `onNewProject()`
  callback prop (the App router calls into the IDE — coordinate ONE mount point in `App.tsx`
  with this session; until then, stub the callbacks with console logs).
- **Don't touch:** any IDE panel, `server.py`, `ConstraintGraph.tsx`.
- **Acceptance:** app boots to Splash; New/Open fire their callbacks; matches the design
  language (no glow, Geist, sage only where meaningful). Component test renders it.

### WP-2 — MCP tools: test + wire the cortex FastMCP surface (the "agent drives cortex" path)
- **Goal:** make `cortex/server.py` (FastMCP) real and trustworthy: expose every tool in
  `contracts.MCP_TOOLS`, prove each returns the correct contract JSON, and provide a real
  **`McpCortex`** client implementing the `CortexClient` protocol so it drops in for
  `FakeCortex` in `conscience/agent_loop.py`.
- **Owns:** `cortex/server.py`, `tests/test_mcp_*.py`, `conscience/mcp_cortex.py` (new).
- **Consumes:** `cortex/*` (orchestrator, repair, bake), `contracts.py`, the
  `CortexClient` protocol in `conscience/cortex_client.py` (import it; don't edit it).
- **Don't touch:** `studio/`, `studio/server.py` (the HTTP one), `ConstraintGraph.tsx`.
- **Acceptance:** in-process MCP client calls `validate_operation`/`suggest_transform`/
  `bake_asset` and gets real verdicts/PAPs (shapes match `contracts.py`); a real-LLM
  agent loop drives a topple→repair episode end-to-end; tests green. Needs `cortex` present
  (see "Prerequisite" below).

### WP-3 — `.wdf` project I/O (open / new / save, wired to the language)
- **Goal:** load a `.wdf` into the studio (populate assets + scene) and save back, via the
  real `conscience.wdf` round-trip.
- **Owns:** `studio/server_wdf.py` (a FastAPI **APIRouter** mounted by `server.py` — so you
  don't edit `server.py`'s body), `studio/src/project.ts` (typed client + project state).
- **Consumes:** `conscience.wdf.{loads,dumps}`, `contracts.py`. A `mountRouter` hook this
  session will add to `server.py` (coordinate: you provide the router, we mount it).
- **Don't touch:** other `studio/src` panels, `cortex/`.
- **Acceptance:** `POST /wdf` parses text → returns assets+scene JSON; `GET /wdf` serializes
  current project; `loads(dumps(x)) == x` honored; tests via FastAPI `TestClient`.

### WP-4 — UE5 commit bridge wiring (headless, mock-tested)
- **Goal:** wire `conscience/ue5/bridge.py` so a validated `commit` reaches UE5 Remote
  Control (negate-X adapter already done + golden-tested), with the optimistic-concurrency
  guard, all proven against a **mock HTTP server** (no Unreal needed).
- **Owns:** `conscience/ue5/commit_flow.py` (new), `tests/test_ue5_commit_*.py`.
- **Consumes:** `conscience/ue5/{adapter,bridge}.py`, `contracts.Diff`.
- **Don't touch:** `studio/`, `cortex/`.
- **Acceptance:** validated diff → canonical→UE5 transform → PUT to mock RC endpoint;
  concurrency mismatch raises and does NOT PUT; the id-map gap (canonical node id ↔ UE5
  actor path — see backend spec §"deferred") is closed with a test.

---

## AFTER M1 SURFACES EXIST — coordinate one slot, then parallel

### WP-5 — Material-confirm UI (the AI-guess → human-confirm → lock loop)
- **Goal:** when `/bake` returns `MaterialGuess[]`, show a confirm panel; user accepts/
  overrides per part; lock folds into the `PAP` (`semantics.materials` + `provenance.locked`).
- **Owns:** `studio/src/MaterialConfirm.tsx`.
- **Consumes:** a `<slot>` this session exposes inside `Properties.tsx`; `MaterialGuess`
  JSON from `/bake`; `theme.css`.
- **Acceptance:** confirm/override/lock updates the PAP; matches `confirm.py` logic; the
  "prebaked" vs "live" mode toggle honored.

### WP-6 — Bake-profiles UI: door / tree / shelf (the moat, surfaced)
- **Goal:** Properties shows the detected archetype + profile params; the Viewport renders
  the **door swept-volume keep-clear** wedge; tree seasonal slider; shelf fill/populate.
- **Owns:** `studio/src/ProfilePanel.tsx`, viewport overlay module for the swept volume.
- **Consumes:** `cortex/bake_profiles/*` (exists), Viewport mount hooks (coordinate).
- **Acceptance:** load the door → see its hinge range + swept wedge; placing furniture in
  the wedge fails `door_clear`.

### WP-7 — Live Rerun stream (Viewport upgrade)
- **Goal:** replace static-`.rrd`-reload with a live `rr.serve` stream so the 3D updates
  continuously. (This is the "graduate Option A → live" step in the backend spec.)
- **Owns:** `studio/server_stream.py` (router), upgrades behind the existing `Viewport`
  interface (coordinate with this session — same endpoints, no UI API change).
- **Acceptance:** version lockstep `rerun-sdk == @rerun-io/web-viewer` (0.33); a CI check
  asserts it; the topple→repair updates without a reload.

---

## LATER PHASES (queue; brief an agent when ready)

- **WP-8 — Asset Studio:** rest-state authoring (demonstrate-don't-configure) + painted
  regions (fill/socket/keep-clear) → richer `PAP.repertoire`. Owns a new `studio/src/Studio*`
  surface + `cortex` rest-state/region modules.
- **WP-9 — Observability + demo:** the 4-minute recorded demo, Rerun timeline polish, the
  scrubable attempt timeline, fallbacks.
- **WP-10 — Vocabularies:** `.wdf` `import "x.vocab"` packs — reusable asset+profile libraries.
- **WP-11 — Buried regression / deformables / other archetypes** from the master spec §6.

---

## Prerequisite for the backend WPs (2, 3, 4)

`node-base-editor` is **conscience-only — no `cortex/`**. Before WP-2/3/4 can call real
physics, `origin/cortex` must be merged onto the integration line (this session does the
M0 merge). Until then, those agents code against the `contracts.py` shapes + `FakeCortex`
and swap to real cortex once it lands — exactly the seam that already worked for the
conscience build.

---

## Dispatch checklist (per agent)

1. Branch: `git switch -c wp-<n>-<slug>` off the integration branch.
2. Paste: this file's "Shared contracts" + the one WP.
3. Constraints: TDD; touch only your WP's files; honor `contracts.py` + `theme.css`; no glow/
   LED-dots/gradients; commit per-file; PR back; don't edit other tracks.
4. Done = the WP's Acceptance line is demonstrably true (tests + a manual check).
