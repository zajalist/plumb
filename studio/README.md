# PLUMB Studio — node-based spatial-validation IDE

A React/TypeScript shell that **replaces Rerun's timeline with a node-based
constraint-graph editor**. It embeds Rerun's web viewer (Rust compiled to Wasm) as a
bare 3D canvas — native panels hidden via panel-state overrides — and renders the
Gallery gate stack (Collision → Stability → Constraints → Reach → Commit) coloured
live from a real `Verdict`. This is the "fork-lite" path: we keep Rerun's 3D guts and
build the chrome around it, with no Rust rebuild.

## Layout

- **Top** — live verdict badge (`STOPPED · STABILITY` red / `ALL GREEN` green) + the
  current stability margin.
- **Middle** — the Rerun 3D scene (timeline/blueprint/selection stripped).
- **Beat bar** — `① placed by vibes` / `② repaired +6cm ✓` pin the bronze offset and the
  3D keyframe; or drag the knob on the bronze node for the continuous in-between.
- **Bottom** — an **editable** constraint canvas (left) + a **node library** (right).

## The editable node editor

The bottom panel is a real authoring canvas, not a static diagram:

- **Move / select / delete** nodes (Delete or Backspace removes the selection).
- **Wire** nodes by dragging between ports — ports are **typed** (object → gold,
  scalar → blue, bool → purple, verdict → green) so only valid connections take.
- **Add** nodes by dragging from the **Library** sidebar onto the canvas.
- **Live compute:** the graph re-evaluates on every edit and every knob move. Drag the
  bronze `x` slider and the `comOverFootprint` measure + `stable` law + `Verdict` flip
  red↔green as the CoM margin crosses the 2 cm threshold (~6.1 cm of offset).

### The .wdf "sentence" model (spec §12.1)

The library is organized the way a `.wdf` sentence reads:

**Assets** (nouns) → **Measures** (read the world) → **Laws** (what must hold, hard/soft)
→ **Verdict**. e.g. *bronze_figure → comOverFootprint → stable → Verdict*.

### Where the numbers come from (honest seam)

`src/engine.ts` is a **client-side stand-in** for Person A's cortex — the conscience is
meant to render truth, not compute it (spec §3, DECISIONS Q3/Q12), but there's no MCP
backend wired to the studio yet. The **stability** law is calibrated to reproduce the
cortex's exact authored numbers (`−7cm` @ x=0, `+1.8cm` @ x=6cm) and interpolates
continuously; the other measures return representative values consistent with the
repaired verdict. Swap `evaluateGraph` for real `validate_operation` calls at
Integration #1 — the graph, ports and renderers don't move.

## Run it

```sh
cd studio
npm install
npm run dev          # open the printed http://localhost:5173/
```

> First load pulls a ~47 MB Wasm viewer — give it a moment.
> The viewer needs **WebGPU/WebGL** (any recent Chrome/Edge).

## Regenerate `gallery.rrd` (required — it is git-ignored)

The viewer loads `/gallery.rrd`, which is intentionally **not committed** (the repo
ignores `*.rrd`). Generate it from the conscience demo before running:

```sh
# from the plumb/ root, with Python 3.13:
py -3.13 -m conscience.demo
# then copy the recording into the app's public dir:
Copy-Item gallery.rrd studio/public/gallery.rrd     # PowerShell
# (bash:  cp gallery.rrd studio/public/gallery.rrd)
```

## Architecture

Two modules carry the design, split so a node type is defined in exactly one place and
the topology actually drives computation:

- **`src/catalog.ts` — the node registry.** Each op has one `NODE_DEFS` entry holding
  *both* its `.wdf` metadata (ports, label, hard/soft) *and* its `evaluate()`. The
  palette grouping (`CATALOG`), the seeded Gallery graph (`seedGraph`), and the evaluator
  all derive from this — add a node = one entry, no switch statements to keep in sync.
- **`src/engine.ts` — the dataflow evaluator.** `evaluateGraph(nodes, edges, scene,
  defByOp)` walks the graph kind-by-kind (typed ports guarantee asset → measure → law →
  verdict), computes each measure **once**, and flows its value along the wire into the
  law it feeds. A law reads the margin from the measure actually wired to it — so
  rewiring changes results; the edges are not decorative. It never switches on `op`; the
  registry is injected. The terminal Verdict is green only when every wired hard law
  passes.

`stableStatus()` is the single "is it stable?" rule, shared by the `stable` law and the
App badge. Visual tokens (`STATUS_COLOR`, `PORT_COLOR`, labels) live once in
`src/theme.ts` and are imported by the canvas and the inspector.

### Honest seam

`engine.ts` is a **client-side stand-in** for Person A's cortex — the conscience is meant
to render truth, not compute it (spec §3, DECISIONS Q3/Q12), but there's no MCP backend
wired to the studio yet. The **stability** law is calibrated to reproduce the cortex's
exact authored numbers (`−7cm` @ x=0, `+1.8cm` @ x=6cm) and interpolates continuously;
the other measures return representative values. Swap the injected `defByOp` /
`evaluateGraph` for real `validate_operation` calls at Integration #1 — the graph, ports
and renderers don't move.

## Key files

- `src/RerunViewer.tsx` — embeds the core `@rerun-io/web-viewer`, hides panels, exposes
  time control + time/selection events.
- `src/ConstraintGraph.tsx` — the editable React-Flow canvas (stateful nodes/edges,
  typed-port wiring, drag-from-palette, delete, live re-evaluation, node renderers).
- `src/engine.ts` — the dataflow evaluator + scene model + measure functions.
- `src/catalog.ts` — the node registry (`NODE_DEFS`) + derived palette + seeded graph.
- `src/theme.ts` — the single source for status/port colours and labels.
- `src/Palette.tsx` — the draggable node library sidebar.
- `src/Inspector.tsx` — the right-hand selected-node inspector.
- `vite.config.ts` — `wasm()` + `topLevelAwait()` plugins, `esnext` target (the viewer
  uses top-level await; WebGPU-capable browsers support it natively).
