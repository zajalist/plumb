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
  stableStatus,
  sweptClear,
  type EvalContext,
  type EvalOutput,
  type NodeKind,
  type NodeOp,
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
  evaluate?: (ctx: EvalContext) => EvalOutput
}

// ── Every node type, defined once ────────────────────────────────────────────
export const NODE_DEFS: NodeDef[] = [
  // Assets (nouns) — the bronze figure's knob is the scene's live value.
  { op: 'bronze_figure', kind: 'asset', label: 'bronze_figure_03', sub: 'top-heavy', provides: 'object', control: 'bronzeX', evaluate: ({ scene }) => ({ value: scene.bronzeX }) },
  { op: 'oak_door', kind: 'asset', label: 'oak_door', sub: 'articulated · swept', provides: 'object', evaluate: () => ({ value: 0 }) },
  { op: 'glass_vase', kind: 'asset', label: 'glass_vase', sub: 'fragile · hollow', provides: 'object', evaluate: () => ({ value: 0 }) },
  { op: 'pedestal', kind: 'asset', label: 'pedestal', sub: 'onSurface', provides: 'object', evaluate: () => ({ value: 0 }) },
  { op: 'walkway', kind: 'asset', label: 'walkway', sub: 'navmesh r=0.45m', provides: 'object', evaluate: () => ({ value: 0 }) },

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

  // Laws — assert on the value flowing in from the wired measure.
  {
    op: 'stable', kind: 'law', label: 'stable', sub: '≥ 2cm', accepts: ['scalar'], provides: 'verdict', hard: true,
    evaluate: ({ inputs }) => {
      const m = asNum(inputs[0])
      if (m === undefined) return { status: 'idle' }
      const s = stableStatus(m)
      return {
        status: s,
        headline: cm(m),
        detail: s === 'pass' ? `CoM ${(m * 100).toFixed(1)}cm inside polygon` : `CoM ${(-m * 100).toFixed(1)}cm outside polygon`,
      }
    },
  },
  {
    op: 'noClip', kind: 'law', label: 'no-clip', sub: '≥ 0', accepts: ['scalar'], provides: 'verdict', hard: true,
    evaluate: ({ inputs }) => {
      const c = asNum(inputs[0])
      if (c === undefined) return { status: 'idle' }
      return { status: c >= 0 ? 'pass' : 'fail', headline: cm(c) }
    },
  },
  {
    op: 'facing', kind: 'law', label: 'facing', sub: '≤ 8°', accepts: ['scalar'], provides: 'verdict', hard: false,
    evaluate: ({ inputs }) => {
      const a = asNum(inputs[0])
      if (a === undefined) return { status: 'idle' }
      return { status: a <= 8 ? 'pass' : 'soft', headline: `${a.toFixed(0)}°` }
    },
  },
  {
    op: 'doorClear', kind: 'law', label: 'door-clear', sub: '== true', accepts: ['bool'], provides: 'verdict', hard: true,
    evaluate: ({ inputs }) => {
      const b = inputs[0]
      if (typeof b !== 'boolean') return { status: 'idle' }
      return { status: b ? 'pass' : 'fail', headline: b ? '✓' : '✗' }
    },
  },
  {
    op: 'walkwayClear', kind: 'law', label: 'walkway', sub: '≥ 90cm', accepts: ['scalar'], provides: 'verdict', hard: true,
    evaluate: ({ inputs }) => {
      const w = asNum(inputs[0])
      if (w === undefined) return { status: 'idle' }
      return { status: w >= 0.9 ? 'pass' : 'fail', headline: `${(w * 100).toFixed(0)} cm` }
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
    },
  }
}

let _seq = 0
export const nextId = (op: string) => `${op}-${++_seq}`

// ── The default Gallery sentence (seed) ──────────────────────────────────────
const COL = { asset: 0, measure: 280, law: 580, verdict: 880 }

export function seedGraph(): { nodes: Node[]; edges: Edge[] } {
  const n = (op: NodeOp, x: number, y: number): Node => specToNode(DEF_BY_OP[op], op, { x, y })

  const nodes: Node[] = [
    n('bronze_figure', COL.asset, 40),
    n('pedestal', COL.asset, 170),
    n('oak_door', COL.asset, 270),
    n('walkway', COL.asset, 370),

    n('comOverFootprint', COL.measure, 30),
    n('clearance', COL.measure, 120),
    n('angleToFront', COL.measure, 210),
    n('sweptClear', COL.measure, 300),
    n('pathWidth', COL.measure, 390),

    n('stable', COL.law, 30),
    n('noClip', COL.law, 120),
    n('facing', COL.law, 210),
    n('doorClear', COL.law, 300),
    n('walkwayClear', COL.law, 390),

    n('verdict', COL.verdict, 200),
  ]

  const e = (s: string, t: string): Edge => ({ id: `${s}->${t}`, source: s, target: t, animated: true })
  const edges: Edge[] = [
    e('bronze_figure', 'comOverFootprint'),
    e('bronze_figure', 'clearance'),
    e('bronze_figure', 'angleToFront'),
    e('pedestal', 'clearance'),
    e('oak_door', 'sweptClear'),
    e('walkway', 'pathWidth'),

    e('comOverFootprint', 'stable'),
    e('clearance', 'noClip'),
    e('angleToFront', 'facing'),
    e('sweptClear', 'doorClear'),
    e('pathWidth', 'walkwayClear'),

    e('stable', 'verdict'),
    e('noClip', 'verdict'),
    e('facing', 'verdict'),
    e('doorClear', 'verdict'),
    e('walkwayClear', 'verdict'),
  ]

  return { nodes, edges }
}
