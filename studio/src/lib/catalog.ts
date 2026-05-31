/**
 * The node registry — the single definition of every node type: its .wdf
 * "sentence" metadata (ports, label) AND its behaviour (`evaluate`). Previously
 * the metadata lived here while two `switch(op)` statements in engine.ts held the
 * behaviour; they drifted. Now one entry defines a node fully — the palette, the
 * seed graph, and the evaluator all read from `NODE_DEFS`.
 */

import type { Edge, Node } from '@xyflow/react'
import {
  angleToFront,
  asNum,
  clearance,
  cm,
  pathWidth,
  stabilityMargin,
  sweptClear,
  type EvalContext,
  type EvalOutput,
  type GateStatus,
  type NodeKind,
  type NodeOp,
  type PlumbData,
  type PortType,
} from './engine'

export type NodeDef = {
  op: NodeOp
  kind: NodeKind
  label: string
  sub?: string
  accepts?: PortType[]
  provides?: PortType
  hard?: boolean
  control?: 'bronzeX'
  /** Default editable threshold (in `tolUnit`) for laws that have one. */
  tol?: number
  /** Display unit of the threshold, e.g. 'cm' or '°'. */
  tolUnit?: string
  /** Comparator shown in the node sub-label. */
  cmp?: '≥' | '≤' | '=='
  evaluate?: (ctx: EvalContext) => EvalOutput
}

/** A law's pass/fail, honouring its hard/soft setting (soft failures warn). */
const lawStatus = (pass: boolean, data: PlumbData): GateStatus =>
  pass ? 'pass' : data.hard === false ? 'soft' : 'fail'

// ── Every node type, defined once ────────────────────────────────────────────
export const NODE_DEFS: NodeDef[] = [
  // Asset (noun). Only the generic `object` is built in; binding it to a real
  // imported/baked asset is the P1 sync. The canvas starts empty — there are no
  // seeded demo nodes anymore.
  { op: 'object', kind: 'asset', label: 'object', sub: 'unbound', provides: 'object', evaluate: () => ({ value: 0 }) },

  // Measures — read the world; compute once, hand the value downstream.
  {
    op: 'comOverFootprint', kind: 'measure', label: 'comOverFootprint', sub: 'margin', accepts: ['object'], provides: 'scalar',
    evaluate: ({ scene, inputs }) => {
      const m = stabilityMargin(asNum(inputs[0]) ?? scene.bronzeX)
      return { value: m, headline: cm(m) }
    },
  },
  {
    op: 'clearance', kind: 'measure', label: 'convex clearance', sub: 'CoACD parts', accepts: ['object'], provides: 'scalar',
    evaluate: ({ scene, inputs }) => {
      const c = clearance(asNum(inputs[0]) ?? scene.bronzeX)
      return { value: c, headline: cm(c) }
    },
  },
  {
    op: 'angleToFront', kind: 'measure', label: 'angle→front', sub: 'to entrance', accepts: ['object'], provides: 'scalar',
    evaluate: () => {
      const a = angleToFront()
      return { value: a, headline: `${a.toFixed(0)}°` }
    },
  },
  {
    op: 'sweptClear', kind: 'measure', label: 'keep_clear(swept)', sub: 'door arc', accepts: ['object'], provides: 'bool',
    evaluate: () => {
      const ok = sweptClear()
      return { value: ok, headline: ok ? '✓' : '✗' }
    },
  },
  {
    op: 'pathWidth', kind: 'measure', label: 'path_clear', sub: 'narrowest gap', accepts: ['object'], provides: 'scalar',
    evaluate: () => {
      const w = pathWidth()
      return { value: w, headline: `${(w * 100).toFixed(0)} cm` }
    },
  },

  // Laws — assert on the value flowing in from the wired measure. Each carries an
  // editable threshold (`tol`, in `tolUnit`) the inspector exposes; `evaluate`
  // reads `data.tol` and falls back to the default here.
  {
    op: 'stable', kind: 'law', label: 'stable', sub: '≥ 2cm', accepts: ['scalar'], provides: 'verdict', hard: true,
    tol: 2, tolUnit: 'cm', cmp: '≥',
    evaluate: ({ inputs, data }) => {
      const m = asNum(inputs[0])
      if (m === undefined) return { status: 'idle' }
      const tol = data.tol ?? 2
      return { status: lawStatus(m * 100 >= tol, data), headline: cm(m), detail: `${(m * 100).toFixed(1)} cm · need ≥ ${tol} cm` }
    },
  },
  {
    op: 'noClip', kind: 'law', label: 'no-clip', sub: '≥ 0cm', accepts: ['scalar'], provides: 'verdict', hard: true,
    tol: 0, tolUnit: 'cm', cmp: '≥',
    evaluate: ({ inputs, data }) => {
      const c = asNum(inputs[0])
      if (c === undefined) return { status: 'idle' }
      const tol = data.tol ?? 0
      return { status: lawStatus(c * 100 >= tol, data), headline: cm(c), detail: `${(c * 100).toFixed(1)} cm · need ≥ ${tol} cm` }
    },
  },
  {
    op: 'facing', kind: 'law', label: 'facing', sub: '≤ 8°', accepts: ['scalar'], provides: 'verdict', hard: false,
    tol: 8, tolUnit: '°', cmp: '≤',
    evaluate: ({ inputs, data }) => {
      const a = asNum(inputs[0])
      if (a === undefined) return { status: 'idle' }
      const tol = data.tol ?? 8
      return { status: lawStatus(a <= tol, data), headline: `${a.toFixed(0)}°`, detail: `${a.toFixed(0)}° · need ≤ ${tol}°` }
    },
  },
  {
    op: 'doorClear', kind: 'law', label: 'door-clear', sub: '== true', accepts: ['bool'], provides: 'verdict', hard: true,
    cmp: '==',
    evaluate: ({ inputs, data }) => {
      const b = inputs[0]
      if (typeof b !== 'boolean') return { status: 'idle' }
      return { status: lawStatus(b, data), headline: b ? '✓' : '✗' }
    },
  },
  {
    op: 'walkwayClear', kind: 'law', label: 'walkway', sub: '≥ 90cm', accepts: ['scalar'], provides: 'verdict', hard: true,
    tol: 90, tolUnit: 'cm', cmp: '≥',
    evaluate: ({ inputs, data }) => {
      const w = asNum(inputs[0])
      if (w === undefined) return { status: 'idle' }
      const tol = data.tol ?? 90
      return { status: lawStatus(w * 100 >= tol, data), headline: `${(w * 100).toFixed(0)} cm`, detail: `${(w * 100).toFixed(0)} cm · need ≥ ${tol} cm` }
    },
  },

  // Fields (context) — no computation for now.
  { op: 'gravity', kind: 'field', label: 'gravity', sub: '−Z · 9.81' },
  { op: 'season', kind: 'field', label: 'season', sub: 'autumn' },

  // Terminal — aggregated by evaluateGraph, not by an evaluate().
  { op: 'verdict', kind: 'verdict', label: 'Verdict', accepts: ['verdict'] },
]

export const DEF_BY_OP: Record<string, NodeDef> = Object.fromEntries(
  NODE_DEFS.map((d) => [d.op, d]),
)

// ── Palette grouping (derived from the registry, by kind) ────────────────────
export type PaletteCategory = { title: string; hint: string; items: NodeDef[] }

const KIND_META: Record<string, { title: string; hint: string }> = {
  asset: { title: 'Assets', hint: 'nouns' },
  measure: { title: 'Measures', hint: 'read the world' },
  law: { title: 'Laws', hint: 'must hold' },
  field: { title: 'Fields', hint: 'context' },
}

export const CATALOG: PaletteCategory[] = (['asset', 'measure', 'law', 'field'] as const).map(
  (k) => ({ title: KIND_META[k].title, hint: KIND_META[k].hint, items: NODE_DEFS.filter((d) => d.kind === k) }),
)

// ── Abstract palette (P0) ─────────────────────────────────────────────────────
// One *general* node per kind; the specific op is chosen in the inspector. This
// is the "abstract the node, specifics in the inspector" decision (SYNC.md D2).
export type AbstractItem = { kind: NodeKind; label: string; hint: string }

export const ABSTRACT_PALETTE: AbstractItem[] = [
  { kind: 'asset', label: 'Object', hint: 'noun · pick in inspector' },
  { kind: 'measure', label: 'Measure', hint: 'reads the world' },
  { kind: 'law', label: 'Law', hint: 'must hold' },
  { kind: 'field', label: 'Field', hint: 'context' },
  { kind: 'verdict', label: 'Verdict', hint: 'roll-up' },
]

/** Every concrete op of a given kind — the inspector's Type dropdown reads this. */
export const OPS_BY_KIND: Record<NodeKind, NodeDef[]> = {
  asset: NODE_DEFS.filter((d) => d.kind === 'asset'),
  measure: NODE_DEFS.filter((d) => d.kind === 'measure'),
  law: NODE_DEFS.filter((d) => d.kind === 'law'),
  field: NODE_DEFS.filter((d) => d.kind === 'field'),
  verdict: NODE_DEFS.filter((d) => d.kind === 'verdict'),
}

/** The op a freshly dragged abstract node starts as (first of its kind). */
export const DEFAULT_OP_BY_KIND: Record<NodeKind, NodeOp> = {
  asset: OPS_BY_KIND.asset[0].op,
  measure: OPS_BY_KIND.measure[0].op,
  law: OPS_BY_KIND.law[0].op,
  field: OPS_BY_KIND.field[0].op,
  verdict: 'verdict',
}

// ── Node construction (data carries metadata only — never the evaluate fn) ───
export function specToNode(def: NodeDef, id: string, position: { x: number; y: number }): Node {
  return {
    id,
    type: def.kind,
    position,
    data: {
      kind: def.kind,
      op: def.op,
      label: def.label,
      sub: def.sub,
      accepts: def.accepts,
      provides: def.provides,
      hard: def.hard,
      control: def.control,
      tol: def.tol,
    },
  }
}

let _seq = 0
export const nextId = (op: string) => `${op}-${++_seq}`

// ── The default graph (seed) ─────────────────────────────────────────────────
// A new project opens to a blank canvas. Nodes arrive either by the user dragging
// from the palette, or auto-spawned for a known asset profile (see PROFILE_GRAPHS).
export function seedGraph(): { nodes: Node[]; edges: Edge[] } {
  return { nodes: [], edges: [] }
}

// ── Profile auto-graphs ──────────────────────────────────────────────────────
// Some baked assets have knowable behaviour, so the editor wires their "sentence"
// for you. Today only a door (articulated → swept volume) auto-spawns; the
// registry shape makes adding tree/shelf/etc. a small change later.

/** True when a baked asset's profile should auto-spawn a constraint subgraph. */
export const DOOR_PROFILES: ReadonlySet<string> = new Set(['door'])
export const profileGraphFor = (profile?: string): ProfileGraphBuilder | undefined =>
  profile && DOOR_PROFILES.has(profile) ? PROFILE_GRAPHS.door : undefined

/** Builds a pre-wired subgraph for an asset, anchored at `origin`. */
export type ProfileGraphBuilder = (
  assetId: string,
  label: string,
  origin: { x: number; y: number },
) => { nodes: Node[]; edges: Edge[] }

/** An Object node already bound to a real imported/baked asset. */
function boundObjectNode(assetId: string, label: string, id: string, position: { x: number; y: number }): Node {
  return {
    id,
    type: 'asset',
    position,
    data: { kind: 'asset', op: 'object', label, assetId, provides: 'object' },
  }
}

export const PROFILE_GRAPHS: Record<string, ProfileGraphBuilder> = {
  // door: [Object(door)] → keep_clear(swept) → door-clear → Verdict
  door: (assetId, label, origin) => {
    const sfx = `${assetId}-${++_seq}`
    const objId = `object-${sfx}`
    const measureId = `sweptClear-${sfx}`
    const lawId = `doorClear-${sfx}`
    const verdictId = `verdict-${sfx}`
    const at = (dx: number, dy: number) => ({ x: origin.x + dx, y: origin.y + dy })

    const nodes: Node[] = [
      boundObjectNode(assetId, label, objId, at(0, 0)),
      specToNode(DEF_BY_OP.sweptClear, measureId, at(280, 0)),
      specToNode(DEF_BY_OP.doorClear, lawId, at(580, 0)),
      specToNode(DEF_BY_OP.verdict, verdictId, at(880, 0)),
    ]
    const e = (s: string, t: string): Edge => ({ id: `${s}->${t}`, source: s, target: t, animated: true })
    const edges: Edge[] = [
      e(objId, measureId),
      e(measureId, lawId),
      e(lawId, verdictId),
    ]
    return { nodes, edges }
  },
}
