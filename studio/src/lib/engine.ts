/**
 * The client-side constraint evaluator — a small "mini-cortex" scoped to the
 * Gallery scene.
 *
 * HONEST SEAM: this is a stand-in for Person A's real cortex. The conscience is
 * meant to *render* truth, not compute it (spec §3, DECISIONS Q3/Q12). With no
 * MCP backend wired to the studio yet, we evaluate the constraint graph locally
 * so authored nodes actually compute. The stability law is calibrated to
 * reproduce the cortex's exact authored numbers (−7cm @ x=0, +1.8cm @ x=6cm);
 * the other measures return representative values. Swap `evaluateGraph` for real
 * `validate_operation` calls at Integration #1 — the graph + registry don't move.
 *
 * The evaluator is **dataflow**: each measure is computed once and its value
 * flows along the wire into the law it feeds. The per-op behaviour lives with
 * each node's definition (see catalog.ts `NODE_DEFS`), injected here as `defByOp`
 * — this module never switches on `op`.
 */

import type { Edge, Node } from '@xyflow/react'

// ── Port datatypes (spec §9.2 typed ports) ──────────────────────────────────
export type PortType = 'object' | 'scalar' | 'bool' | 'verdict'

// ── Node categories (the .wdf "sentence" model, spec §12.1) ──────────────────
export type NodeKind = 'asset' | 'measure' | 'law' | 'field' | 'verdict'

/** Which concrete asset/measure/law/field a node is. */
export type NodeOp =
  | 'bronze_figure' | 'oak_door' | 'glass_vase' | 'pedestal' | 'walkway'
  | 'comOverFootprint' | 'clearance' | 'angleToFront' | 'sweptClear' | 'pathWidth'
  | 'stable' | 'noClip' | 'facing' | 'doorClear' | 'walkwayClear'
  | 'gravity' | 'season'
  | 'verdict'

export type GateStatus = 'pass' | 'fail' | 'soft' | 'idle'

/** The data every PLUMB node carries (shared by the canvas + inspector). */
export type PlumbData = {
  kind: NodeKind
  op: NodeOp
  label: string
  sub?: string
  accepts?: PortType[]
  provides?: PortType
  hard?: boolean
  control?: 'bronzeX'
}

/** Evaluation result merged into a node's data for rendering. */
export type NodeResult = {
  status: GateStatus
  headline?: string
  detail?: string
}

/** The editable scene the graph evaluates against. */
export type SceneState = {
  /** Bronze figure x-offset in metres; the live "knob". 0 = topple, ~0.06 = safe. */
  bronzeX: number
}

export const INITIAL_SCENE: SceneState = { bronzeX: 0 }

export const BRONZE_X_MIN = 0
export const BRONZE_X_MAX = 0.12
export const STABLE_THRESHOLD_M = 0.02 // law: margin ≥ 2cm

// ── Dataflow contracts ───────────────────────────────────────────────────────
/** A value carried along a wire (a measure's output, an asset's knob). */
export type PortValue = number | boolean | undefined

/** What a node's `evaluate` receives: the scene + the values on its incoming wires. */
export type EvalContext = { scene: SceneState; inputs: PortValue[]; data: PlumbData }

/** What a node's `evaluate` returns: a downstream value and/or a display status. */
export type EvalOutput = {
  value?: PortValue
  status?: GateStatus
  headline?: string
  detail?: string
}

/** The slice of a node definition the evaluator needs (catalog.ts provides the full one). */
export type EvalDef = {
  kind: NodeKind
  hard?: boolean
  evaluate?: (ctx: EvalContext) => EvalOutput
}

export const asNum = (v: PortValue): number | undefined =>
  typeof v === 'number' ? v : undefined

// ── Measures (real numbers) ──────────────────────────────────────────────────

/**
 * Quasi-static CoM-over-support-polygon margin (metres) as a function of the
 * bronze figure's x-offset. Linear calibration through the cortex's two authored
 * points: margin(0) = −0.07, margin(0.06) = +0.018.
 */
export function stabilityMargin(bronzeX: number): number {
  return 1.467 * bronzeX - 0.07
}
export function clearance(bronzeX: number): number {
  return 0.042 + 0.15 * bronzeX
}
export function angleToFront(): number {
  return 4.0
}
export function sweptClear(): boolean {
  return true
}
export function pathWidth(): number {
  return 0.94
}

/** The single rule for "is it stable?" — used by the law's evaluate AND the App badge. */
export function stableStatus(margin: number): GateStatus {
  return margin >= STABLE_THRESHOLD_M ? 'pass' : 'fail'
}

/** Format metres as a signed cm string. */
export const cm = (m: number) => `${m >= 0 ? '+' : ''}${(m * 100).toFixed(1)} cm`

// ── Graph walk (dataflow) ─────────────────────────────────────────────────────

/**
 * Evaluate the wired graph against the scene; returns a result per node.
 *
 * Typed ports guarantee edges only run asset → measure → law → verdict, so we can
 * evaluate kind-by-kind. Each node's `evaluate` gets the values produced by its
 * upstream neighbours (real dataflow — a law reads the margin from the measure
 * wired into it, not a recomputation). An unwired law reads `idle`. The terminal
 * Verdict is green only when every wired HARD law passes.
 */
export function evaluateGraph(
  nodes: Node[],
  edges: Edge[],
  scene: SceneState,
  defByOp: Record<string, EvalDef>,
): Map<string, NodeResult> {
  const outputs = new Map<string, PortValue>()
  const results = new Map<string, NodeResult>()
  const sourcesOf = (id: string) => edges.filter((e) => e.target === id).map((e) => e.source)
  const lawResults: { hard: boolean; status: GateStatus }[] = []

  const data = (n: Node) => n.data as PlumbData
  const byKind = (k: NodeKind) => nodes.filter((n) => data(n).kind === k)

  for (const kind of ['asset', 'field', 'measure', 'law'] as const) {
    for (const n of byKind(kind)) {
      const d = data(n)
      const def = defByOp[d.op]
      const srcs = sourcesOf(n.id)

      // An unwired law has nothing to judge.
      if (kind === 'law' && srcs.length === 0) {
        results.set(n.id, { status: 'idle', detail: 'unwired' })
        continue
      }

      const inputs = srcs.map((s) => outputs.get(s))
      const out = def?.evaluate ? def.evaluate({ scene, inputs, data: d }) : {}
      if (out.value !== undefined) outputs.set(n.id, out.value)
      results.set(n.id, { status: out.status ?? 'idle', headline: out.headline, detail: out.detail })

      if (kind === 'law') lawResults.push({ hard: d.hard ?? true, status: out.status ?? 'idle' })
    }
  }

  // Terminal verdict: AND of wired hard laws (mirrors the gate-stack discipline).
  const firstHardFail = lawResults.find((l) => l.hard && l.status === 'fail')
  for (const n of byKind('verdict')) {
    results.set(
      n.id,
      firstHardFail
        ? { status: 'fail', detail: 'blocked' }
        : lawResults.length
          ? { status: 'pass', detail: 'all hard laws pass · commit' }
          : { status: 'idle', detail: 'no laws wired' },
    )
  }

  return results
}
