# PLUMB Studio — node-based spatial-validation IDE

A React/TypeScript shell that **replaces Rerun's timeline with a node-based
constraint-graph editor**. It embeds Rerun's web viewer (Rust compiled to Wasm) as a
bare 3D canvas — native panels hidden via panel-state overrides — and renders the
Gallery gate stack (Collision → Stability → Constraints → Reach → Commit) coloured
live from a real `Verdict`. This is the "fork-lite" path: we keep Rerun's 3D guts and
build the chrome around it, with no Rust rebuild.

## Layout

- **Top** — verdict badge (`STOPPED · STABILITY` red / `ALL GREEN` green).
- **Middle** — the Rerun 3D scene (timeline/blueprint/selection stripped).
- **Scrubber** — `attempt 1 / attempt 2 ✓` replaces the timeline; selecting an attempt
  recolours the graph **and** seeks the 3D viewer's time cursor.
- **Bottom** — the React-Flow constraint graph; gate nodes glow green/amber/red.

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

## Where the data comes from

`src/verdicts.json` is generated from a real `conscience.agent_loop.run_episode` over
the Gallery scene — the same numbers the cortex produced (Stability `−7cm` → `+1.8cm`).
The JS viewer API exposes time/selection but not component values, so the graph reads
verdicts from this file and stays in sync with the 3D scene via the time cursor. A live
pipeline would switch the source to `rr.serve()` gRPC.

## Key files

- `src/RerunViewer.tsx` — embeds the core `@rerun-io/web-viewer`, hides panels, exposes
  time control + time/selection events.
- `src/ConstraintGraph.tsx` — the React-Flow graph (selectors → operators → gate sinks).
- `src/verdicts.ts` / `verdicts.json` — typed verdict data per attempt.
- `vite.config.ts` — `wasm()` + `topLevelAwait()` plugins, `esnext` target (the viewer
  uses top-level await; WebGPU-capable browsers support it natively).
