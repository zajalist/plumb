/**
 * Connection logic for the constraint canvas — kept separate from the React
 * component so the wiring rules are testable in isolation.
 *
 * Flow (strict, directional): a wire is dragged FROM an output port (right) and
 * dropped ON an entry port (left). React Flow's strict connection mode enforces
 * source→target, so the in-progress line starts from the output you grabbed and
 * can only land on an entry — no ambiguity about which circle the preview snaps to.
 *
 * INVARIANT — one wire per entry port: each input/left circle holds at most one
 * incoming wire (a new wire onto an already-wired entry replaces the old one).
 * Output ports may still fan out to many. The single exception is the Verdict
 * node, which aggregates every law wired into it to compute the final pass/fail.
 */
import { addEdge, type Connection, type Edge } from '@xyflow/react'
import type { NodeKind, PlumbData } from './engine'

/** Look up a node's PlumbData by id (wraps ReactFlow's getNode). */
export type GetNodeData = (id: string) => PlumbData | undefined

/** The only node kind whose entry port accepts more than one wire. */
const MULTI_INPUT_KINDS: ReadonlySet<NodeKind> = new Set<NodeKind>(['verdict'])

/** True when `src` provides a port type that `tgt` accepts. */
function typeOk(src?: PlumbData, tgt?: PlumbData): boolean {
  const provides = src?.provides
  const accepts = tgt?.accepts
  return !!provides && !!accepts && accepts.includes(provides)
}

/**
 * Valid when the source's output type is accepted by the target's entry.
 * Strict mode already guarantees source = an output port and target = an entry,
 * so this is a straight provides → accepts type check. Drives `isValidConnection`
 * (lights up compatible entries while dragging).
 */
export function canConnect(conn: Connection | Edge, getData: GetNodeData): boolean {
  if (!conn.source || !conn.target || conn.source === conn.target) return false
  return typeOk(getData(conn.source), getData(conn.target))
}

/**
 * Apply a dropped connection to the edge list, enforcing the one-wire-per-entry
 * invariant (Verdict excepted). Returns the list unchanged if the drop is invalid.
 */
export function connect(edges: Edge[], conn: Connection, getData: GetNodeData): Edge[] {
  if (!canConnect(conn, getData) || !conn.target) return edges

  const targetKind = getData(conn.target)?.kind
  const aggregates = !!targetKind && MULTI_INPUT_KINDS.has(targetKind)

  // One wire per entry: drop any existing wire into this target first (unless it
  // aggregates, like Verdict).
  const base = aggregates ? edges : edges.filter((e) => e.target !== conn.target)

  return addEdge({ ...conn, animated: true }, base)
}
