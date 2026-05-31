# Node editor: empty-by-default canvas, profile auto-graphs, edge feedback

**Date:** 2026-05-31
**Branch:** node-editor
**Status:** approved

Three linked changes to the studio constraint-graph node editor
(`studio/src/components/ConstraintGraph.tsx`, `studio/src/lib/catalog.ts`,
`studio/src/lib/engine.ts`, `studio/src/components/Inspector.tsx`,
`studio/src/App.tsx`).

## Motivation
- New projects open to a cluttered seeded "template" graph of stubbed demo nodes.
  It should be empty.
- Importing/baking an object changes nothing in the editor unless the user wires
  it by hand — even for assets whose behaviour is knowable (a door's swing).
- Typed-port rejections are silent: dragging `keep_clear(swept)` (a `bool`) onto
  the Verdict node, or onto `stable` (a `scalar` law), fails with no explanation.
  Both rejections are *correct*; the lack of feedback is the bug.

## A. Empty canvas + remove demo stubs
- `seedGraph()` returns `{ nodes: [], edges: [] }`. A new project = blank canvas.
- Remove the named demo assets entirely — `bronze_figure`, `oak_door`,
  `glass_vase`, `pedestal`, `walkway` — from `NODE_DEFS` and the `NodeOp` union.
  The only built-in asset op is the generic `object` (unbound).
- The Object node's inspector dropdown becomes: **Imported assets** optgroup + a
  single "— unbound —" option. The "Demo assets" optgroup is removed.
- The bronze-knob control block in `Inspector.tsx` (keyed on `control:'bronzeX'`)
  is removed — no node carries that control anymore. `engine.ts`'s stability math
  (`stabilityMargin`, etc.) stays as the local fallback evaluator.
- Fields (`gravity`, `season`) stay as Field-kind library options (the Field
  palette node needs ≥1 concrete op); they are not seeded onto the canvas.

## B. Profile auto-graphs (door)
- New registry `PROFILE_GRAPHS: Record<string, (assetId, label, origin) => {nodes, edges}>`
  in `catalog.ts`. One entry today: `door`.
- `ObjectOption` gains `profile?: string`, sourced from `pap.profile` in `App.tsx`.
- A door is detected via `pap.profile === 'door'` (the base archetype that the
  door-family presets bake to — see `bakeCatalog.PROFILE_BASE`). Detection is
  centralized in one helper so it is easy to broaden later.
- When a baked asset with `profile === 'door'` first appears in `objects`,
  `ConstraintGraph` auto-spawns its subgraph, pre-bound to the asset:
  ```
  [Object: <door>] -> keep_clear(swept) -> door-clear -> Verdict
  ```
- Lifecycle: a `materializedAssets` Set tracks auto-added assets so we never
  duplicate and never re-add after the user deletes them. Each new door asset is
  placed at an offset origin so multiple doors stack cleanly. Non-door assets add
  nothing (canvas stays empty; user binds an Object node manually).

## C. Edge-connection feedback (keep strict, explain failures)
- Keep the strict typed flow: asset -> measure -> law -> verdict. No loosening.
- Add `onConnectEnd(event, connectionState)`: when `connectionState.isValid` is
  false and the drag ended on a node/handle, show a transient toast in the canvas
  explaining why, computed from the source `provides` vs target `accepts`:
  - measure->law type mismatch: name both types, suggest a compatible law
    (e.g. a `bool` measure -> "try door-clear").
  - measure->verdict: "Verdict only accepts a Law's output — wire this measure
    into a Law first."
- The toast auto-dismisses (~3s) and is styled to match the studio palette.

## Non-goals
- Orphan cleanup when an asset is deleted from the panel (bound nodes remain).
- Profiles beyond `door` (the registry makes adding `tree`/`shelf` a small later
  change).
- Loosening the type system or auto-inserting laws.

## Files touched
- `studio/src/lib/engine.ts` — trim `NodeOp` union (drop demo asset ops).
- `studio/src/lib/catalog.ts` — drop demo asset `NODE_DEFS`; empty `seedGraph()`;
  add `PROFILE_GRAPHS` + door template + door-detection helper.
- `studio/src/components/ConstraintGraph.tsx` — empty seed; `objects`-watch
  effect for profile auto-graphs; `onConnectEnd` invalid-drop toast + toast UI.
- `studio/src/components/Inspector.tsx` — dropdown relabel (Imported + unbound);
  remove bronze control block.
- `studio/src/App.tsx` — add `profile` to the `objects` mapping.
- `studio/src/App.css` — toast styles.
</content>
</invoke>
