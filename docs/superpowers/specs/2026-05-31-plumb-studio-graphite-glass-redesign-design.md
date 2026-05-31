# PLUMB Studio — Graphite-Glass UI Redesign + Teammate Merge

**Date:** 2026-05-31
**Status:** Approved design (brainstorm complete)
**Scope:** Replace the warm "austere instrument" theme with a cool graphite + Aero-glass design language modeled on Gaea (QuadSpinner) and retro Unreal Engine 4, and fold in the teammate branches it has to sit on top of.

---

## 1. Goal

Make PLUMB Studio read like a *professional spatial-validation tool*, not an AI-generated web app. The prior warm austere theme and the abandoned `redesign` branch's Frutiger-Aero glass both miss: the warm palette feels soft, and the panels' internals were static label→text rows floating in space. Real editors (Gaea, UE4) read professional because every value lives in a **recessed widget**, sections **collapse**, and numbers are **tabular sans** — the "chrome" is functional, dense, and tactile.

This redesign replaces the theme **wholesale** (no theme toggle) and applies one consistent field system across every surface.

---

## 2. Locked design language

The reference mockups live in `.superpowers/brainstorm/` (git-ignored). The agreed direction:

- **Palette — cool graphite, single teal accent.** Near-black canvas, frosted translucent panels, teal for "good/pass", terracotta for "fail", amber for "soft". Warm olive/cream is retired.
- **Glass — restrained Aero.** Frosted translucent panels with a top-gloss highlight and a hairline light border. Subtle, not the heavy wet gloss of the old `redesign` branch.
- **Typography — native Windows pro fonts.** Segoe UI / Segoe UI Variable for everything, **tabular numerals** for all numbers. Mono (Cascadia Mono) reserved for IDs only. No Geist/Inter (the "AI" tell), no characterful typewriter mono for readouts.
- **Field system — UE4 bones + Gaea sliders.** Category header bands with collapse chevrons; recessed input fields; numeric scalars get a **teal proportional fill-bar** behind the value (Gaea style); vectors split into **per-axis cells**; dropdowns, checkboxes, toggles; alternating row tint.
- **No editorializing.** Sections are `PHYSICS`, `MATERIALS` — never "— guessed" or other em-dash annotations. Real software does not narrate its own fields.
- **Watermark belongs on the canvas** (viewport / node graph), like UE's faded "BLUEPRINT" — never inside property panels.

### Concrete tokens (`theme.css` `:root`)

```
--bg:#0E1012;  --canvas:#0C0E10;
--ink:#E7EAEC; --ink2:#98A1A9; --ink3:#626B72; --ink4:#474E54;
--teal:#34C0AD;            /* accent + pass */
--fail:#E0694F; --amber:#D9A84C;   /* gate fail / soft */
--field:#0C0F11; --field-b:#2B3236;
--glass-b:rgba(255,255,255,.08); --glass-hi:rgba(255,255,255,.07);
--sans:'Segoe UI','Segoe UI Variable',system-ui,sans-serif;
--mono:'Cascadia Mono','Cascadia Code',ui-monospace,Consolas,monospace;
```

- Panel glass: `linear-gradient(180deg, rgba(44,51,57,.6), rgba(22,26,29,.66))` + `backdrop-filter:blur(14px) saturate(1.1)` + `inset 0 1px 0 var(--glass-hi)` + soft drop shadow; a `.glass::before` gloss over the top ~50%.
- Radii: panels ~7px, fields ~3px.
- Gate colors: pass = teal, fail = terracotta with `inset 0 -2px 0 var(--fail)` underline, soft = amber.

---

## 3. Branch & merge strategy

> **Revised after inspecting the live repo.** The original "start from `main`" plan assumed `node-editor ⊆ main`. Reality: `node-editor` has **diverged** from `origin/main` — it carries unpushed feature work (UE `.uasset → glTF` convert pipeline, `/bake_cached`, "Open .wdf", bake-staging screen, masks-in-viewport) that `main` lacks, while `main` carries Fara's PR #7 node-editor upgrades + a studio `components/`+`lib/` reorg that `node-editor` lacks. Decision (user-confirmed): **redesign on `node-editor`, defer the `main` integration.**

1. **Protect WIP first** — the ~165 lines of uncommitted work were committed as a checkpoint (`2aee6a4`) before any redesign edit, so nothing can be lost.
2. **Redesign directly on `node-editor`** — preserves the pipeline work; no rebase, no branch switch that could strand it.
3. **Defer the `main` ↔ `node-editor` integration** — folding Fara's node-editor upgrades + the studio reorg is a separate, conflict-prone step handled after the redesign, coordinated with Fara. `conscience` (`.wdf` fixes) folds in during that same later integration, not now.
4. **Abandon the old `redesign` branch** — its Frutiger-Aero glass CSS is superseded by the new token system.
5. **Node-editor restyle is its own late commit** — we edit `components/ConstraintGraph.tsx` styling directly; isolating it keeps the visual diff legible and easy to reconcile during the later `main` merge.

---

## 4. Token system + glass foundation

Rewrite `studio/src/theme.css`:
- Replace the warm `:root` vars with the cool token set above.
- Replace base element styles (body bg/ink, fonts) accordingly; default `font-variant-numeric: tabular-nums` on numeric utility classes.
- Add a `.glass` utility (frosted panel + top-gloss `::before`) used by every panel shell.
- Keep the existing structural class names where components still rely on them, but migrate panel internals onto the new primitives (Section 5).

No backend change — `studio/server.py`, `cortex/`, `conscience/` are untouched by the redesign.

---

## 5. Reusable UI primitives

New, in `studio/src/components/ui/` — built once, shared across surfaces:

| Primitive | Responsibility | Used by |
|---|---|---|
| `GlassPanel` | Frosted shell + optional header (icon, title, right meta) | every panel |
| `CategoryBand` | Collapsible section header (chevron + uppercase label); owns collapse state | Properties, Inspector |
| `Field` | Recessed input shell | Inspector, Properties |
| `FillBarField` | `Field` + teal proportional fill behind a tabular value/unit (`value`, `max`, `unit`) | Properties (mass, confidence), Inspector |
| `VectorField` | N per-axis recessed cells | Properties (CoM), Inspector (pos/scale) |
| `Dropdown` | Styled select | Properties (material picker) |
| `Toggle` / `Checkbox` | Boolean control | Properties (hollow), Inspector |
| `Swatch` | Material color chip | Properties |
| `Button` | Flat recessed action | Confirm & Lock, Inspector actions |

Each primitive has one clear purpose, a typed prop interface, and can be tested in isolation. Panels become thin compositions of primitives instead of ad-hoc markup.

---

## 6. Surface-by-surface restyle map

| Surface | Result |
|---|---|
| **Menubar / brand** | Graphite glass bar. Wordmark: keep Instrument Serif "Plumb", recolored to a cool tone to sit in the palette (revisitable). |
| **Gate strip** (`GateStack.tsx`) | Glass segmented bar; teal pass / terracotta fail underline / amber soft; tabular values; commit cell. Update `GateStack.test.tsx` to new markup, keep green. |
| **Assets panel** (`AssetsPanel.tsx`) | Graphite list, recessed thumbnails, dropzone; selected row gets a teal left-edge. |
| **Viewport** (`Viewport.tsx`) | Cool canvas + faint node grid, crop marks, watermark on the canvas; CoM/ghost overlays recolored (teal = valid, terracotta = toppled ghost); Three.js mesh material neutralized off sage. |
| **Properties** (`Properties.tsx`) | The locked panel: UE4 category bands + Gaea fill-bar numerics + per-axis CoM cells + material dropdowns. Update `Properties.test.tsx`, keep green. |
| **Node editor** (`components/ConstraintGraph.tsx`) | React-Flow nodes → graphite-glass cards, recessed ports, teal active wires, category-style headers; dot-grid canvas + watermark. Isolated late commit (Section 3.4). |
| **Inspector** (`components/Inspector.tsx`) | Placement controls as `Field`/`VectorField` + flat `Button`s. |
| **Splash** (`Splash.tsx`) | Graphite glass launch card; recent list, New/Open actions. Update `Splash.test.tsx`, keep green. |

---

## 7. Verification

- **Component tests stay green** — `Properties.test`, `GateStack.test`, `Splash.test` rewritten to the new markup; `npm test` passes.
- **Backend untouched** — `pytest -q` still green (237 tests; redesign changes no Python).
- **Visual pass** — run the studio dev server + backend, confirm the live bake → validate → repair → commit loop renders correctly in the new look across every surface; confirm no glows/AI-default fonts/em-dash annotations slipped in.

---

## 8. Out of scope (YAGNI)

- No theme toggle / no preserving the warm austere palette.
- No new features — purely visual + the teammate merge it sits on.
- No speculative component library beyond the primitives the panels actually use.
- No backend, cortex, conscience, or contract changes (beyond folding the existing `conscience` `.wdf` fixes).
- Wordmark redesign deferred (kept serif, recolored).
