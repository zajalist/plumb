# PLUMB Studio — Backend Playground + Bake Workbench — Design Spec

**Date:** 2026-05-30
**Branch:** `node-base-editor` (frontend `studio/`)
**Owners:** zajalist + Claude (this spec) · FaraDuMatin owns the node editor (separate, consumes the same JSON)

---

## 1. Purpose

Turn `studio/` from a **pre-recorded `.rrd` player** (it currently replays a frozen
`gallery.rrd` made by `FakeCortex`) into a **live authoring IDE driven by the real
Python cortex** — so we can actually exercise our physics + bake ML by hand.

The user's flow (the product, in one line):

> **Open/new a `.wdf` → import 3D meshes → click one → see it in the viewport + its
> baked physics in Properties → author validation in the node editor.**

The first thing *we* build (the "blue path") is **import → bake → Properties**: drop a
mesh, the backend runs the real composition bake, and the Properties panel shows the
real mass / centre-of-mass / inertia / materials / hollowness. That is the surface that
tests the bake + material-guess ML. The validate→repair gate loop is the second slice.

**Out of scope (Fara owns):** the node-editor canvas + palette (`ConstraintGraph.tsx`).
We coordinate only on the `App.tsx` layout slot and the shared verdict/PAP JSON.

---

## 2. Architecture

Browser UI cannot run Python physics (`trimesh`, `coacd`, `scipy`). So a small Python
backend holds the real `cortex` and answers HTTP requests from the studio.

**Decision (locked): Option A — request/response HTTP** (not a live gRPC stream).
Each endpoint is one real cortex call, directly `curl`-able and unit-testable; the 3D
reloads the regenerated recording per action. Graduates to a live stream later behind
the same endpoints without UI changes.

```
 studio (React/Vite, browser)            studio/server.py (FastAPI)         cortex/ (Python)
 ┌───────────────────────────┐  HTTP    ┌──────────────────────────┐      ┌──────────────┐
 │ Assets · Viewport ·        │ ───────▶ │ POST /bake   (file)      │ ───▶ │ bake_asset   │
 │ Properties · Gate Stack    │          │ POST /validate (diff)    │ ───▶ │ validate_op  │
 │ + Fara's node editor       │ ◀─────── │ POST /repair (obj,intent)│ ───▶ │ suggest_xform│
 │ (renders Verdict/PAP JSON) │  JSON    │ POST /commit             │      │ world model  │
 └───────────────────────────┘          │ GET/POST /wdf (load/save)│ ───▶ │ conscience.wdf│
                                         └──────────────────────────┘      └──────────────┘
```

- **Shared contract:** the frozen `contracts.py` (`PAP`, `Verdict`, `Diff`, `GateResult`,
  `MaterialGuess`). The frontend mirrors these as TypeScript types (extend the existing
  `studio/src/verdicts.ts`). Backend returns `model_dump()` of the contract objects.
- **Prerequisite:** `node-base-editor` is conscience-only — **no `cortex/`**. Step 0 is
  bringing `origin/cortex` onto this line (merge to an integration branch) so `server.py`
  can `import cortex`. Until then `/bake` etc. can run against a thin stub, but the real
  test needs cortex present.

---

## 3. Layout (approved)

Matches the current studio shell (viewport-ish on top, node editor full-width bottom),
with the top split three ways:

```
┌ menubar: ◆PLUMB │ New · Open · Import mesh ········· the_gallery.wdf · 3 assets ┐
├ GATE STACK:  collision +4cm ›  stability −7cm  › constraints idle › reach idle … commit ┤
├──────────────┬─────────────────────────────────────┬───────────────────────────┤
│  ASSETS      │            VIEWPORT                  │   PROPERTIES — PAP        │
│  (thumbnails)│        (dark device, selected asset) │   mass / CoM / materials  │
├──────────────┴─────────────────────────────────────┴───────────────────────────┤
│  NODE EDITOR + palette — full width                                    (Fara)   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

- **Assets** (left ~248px) — imported meshes with **live faceted thumbnails**, click to select.
- **Viewport** (center) — dark "device" stage rendering the selected asset; CoM marker +
  plumb-line overlay when a verdict is present.
- **Properties** (right ~288px) — the baked **PAP**: identity, physics, materials (with
  the AI-guess + "confirm & lock" loop).
- **Gate Stack** (strip under menubar) — `collision › stability › constraints › reach …
  commit`, flat, status by color only.
- **Node editor** (full-width bottom) — **Fara**.

---

## 4. Visual design system (approved — "austere instrument")

The non-negotiable rules (these are what keep it from looking generic/AI):

- **No glows, no LED status-dots, no decorative drop-shadows, no gradient fills.** Flat,
  matte surfaces; structure via **1px hairlines** and generous whitespace.
- **Brand:** the real `plumb.svg` aperture mark (sage `#586040`, olive bevel `#424A29`).
  Sage is used *only* where it earns meaning (selection, pass, brand, the confirm CTA).
- **Palette (dark, warm):** bg `#16150F`, surface `#1C1B14`, inset `#100F0A`, hairline
  `#2C2A20`/`#39362A`, ink `#EAE6D7`/`#ADA994`/`#7C7868`. Sage `#8E9A60`/`#586040`.
  **Gate semantics are the only saturated colors:** pass = sage `#8E9A60`, soft = ochre
  `#C2A24E`, fail = terracotta `#C16A4A` (never neon red).
- **Type:** Geist (UI) + Geist Mono (all measured values, filenames, tabular numerics).
- **Icons:** a custom inline-SVG set built from the aperture geometry, each glyph encoding
  its concept (stability = plumb-line-to-base, collision = two offset apertures, reach =
  path threading nodes, com = offset datum in a frame, mass = weighted volume, import =
  arrow into a tray, etc.). **No icon libraries, no emoji.**
- **Asset thumbnails:** faceted, flat-shaded 3D previews. v1 = a real client-side render
  of the imported mesh (small offscreen Three.js render to a canvas/data-URL); the
  hand-drawn facets in the mockup are the visual target.

Reference mockup (the approved look): `.superpowers/brainstorm/design/dir-reductive.html`
and the refined `.superpowers/brainstorm/.../refined.html`.

---

## 5. Components & contracts

### Backend — `studio/server.py` (FastAPI)
| Endpoint | Body | Returns | Cortex call |
|---|---|---|---|
| `POST /bake` | multipart mesh file (+ optional material map) | `PAP` JSON + thumbnail hint | `cortex.bake.bake_asset` |
| `POST /validate` | `Diff` | `Verdict` JSON | `cortex.orchestrator.validate_operation` |
| `POST /repair` | `{object, intent}` | `Transform` JSON | `cortex.repair.suggest_transform` |
| `POST /commit` | `Diff` | `{ok}` | world model |
| `GET /wdf` / `POST /wdf` | — / `.wdf` text | document / ok | `conscience.wdf.loads/dumps` |
| `GET /health` | — | `{ok, cortex: bool}` | — |

- Stateless per call except an in-memory world/asset registry (a module-level
  `WorldModel` + `{asset_id: PAP}`), reset on restart. CORS open to the Vite dev origin.
- Returns contract objects via `.model_dump()`. Errors → `{error, detail}` + 4xx/5xx.

### Frontend (studio/src) — **ours**
- `api.ts` — typed `fetch` wrappers for the endpoints; mirrors `contracts.py` shapes.
- `AppShell` / update `App.tsx` — the menubar + three-column top + node-editor slot.
- `AssetsPanel.tsx` — import (drop/file), the asset list, thumbnails, selection state.
- `Viewport.tsx` — render the selected mesh (Three.js or the existing Rerun viewer);
  overlay CoM + plumb line from the verdict.
- `Properties.tsx` — render a `PAP`: identity / physics / materials + confirm-lock.
- `GateStack.tsx` — the flat strip from a `Verdict`.
- `Inspector` (controls: Validate / Repair / Commit + transform nudge) — slice 2.
- `theme.css` — the design tokens + the custom SVG icon `<symbol>` sheet.

### Frontend — **Fara**
- `ConstraintGraph.tsx` — unchanged ownership; consumes the same `Verdict`/`PAP` JSON.

---

## 6. Data flow

**Bake path (slice 1 — the ML test):**
`Import mesh → api.bake(file) → server /bake → cortex.bake_asset → PAP → Properties renders
real mass/CoM/materials; Viewport renders the mesh; AssetsPanel adds a thumbnail.`

**Validate→repair path (slice 2):**
`Place/select → api.validate(diff) → /validate → orchestrator → Verdict → GateStack +
Viewport overlay; on fail → api.repair → /repair → suggest_transform → re-validate → green.`

**Project path:** `New/Open .wdf → /wdf → conscience.wdf.loads → populate assets/scene;
Save → dumps.`

---

## 7. Error handling

- Backend down / cortex missing → `GET /health` drives a clear banner ("backend offline"
  / "cortex not linked"); panels show empty states, never silent failure.
- Bake failure (bad mesh, CoACD error) → `/bake` returns `{error}`; the asset shows a
  red "bake failed" state in the list with the message; the app stays usable.
- Version note: any live-Rerun path must keep `rerun-sdk` == web-viewer version (0.33).
- All numbers shown come straight from the verdict/PAP — no client-side physics, ever.

---

## 8. Testing

- **Backend:** `pytest` against FastAPI `TestClient` — `/bake` on the two-part fixture
  returns a PAP whose CoM sits above the geometric centroid (the composition proof);
  `/validate` on a topple diff returns `stopped_at == stability`, negative margin;
  `/repair` flips it green. Endpoint shapes match `contracts.py`.
- **Frontend:** component tests render `Properties`/`GateStack` from fixture JSON and
  assert the real numbers + states appear; an `api.ts` test hits a mocked server.
- **Manual:** import the bronze figure → Properties shows 48 kg, high CoM, bronze/stone.

---

## 9. Build phasing (one plan, two milestones)

- **M0 — wiring:** integrate `cortex` onto this branch; `server.py` skeleton + `/health`;
  `theme.css` (tokens + icon sheet); `api.ts`. Studio shell adopts the new layout + design.
- **M1 — Bake Workbench (the ML test):** Import → `/bake` → Properties (PAP) + Viewport
  render + Assets thumbnails. **Done = drop a mesh, see its real baked physics.**
- **M2 — Validate/Repair:** Gate Stack + Inspector (Validate/Repair/Commit) against real
  `/validate` + `/repair`. **Done = topple→repair on real cortex, in the studio.**
- **M3 (later):** `.wdf` open/save in-app; live Rerun stream; material-confirm UI polish.

---

## 10. Risks

- **No cortex on this branch** — must merge it first (M0); otherwise only `FakeCortex`.
- **Three.js vs Rerun for the viewport** — the existing `RerunViewer` loads `.rrd`; for a
  live single-mesh render Three.js is simpler. M0 picks one (lean: Three.js for the asset
  viewport, keep Rerun for the verdict recording if/when we stream).
- **Scope creep into Fara's node editor** — hard boundary: we never edit `ConstraintGraph.tsx`.
