/**
 * Connection logic for the constraint canvas — kept separate from the React
 * component so the wiring rules are testable in isolation.
 *
 * Flow (loose mode): drag from a node's port, release anywhere over the target
 * node. A connection is valid when one orientation is a type-correct
 * provides → accepts pairing (object→object, scalar→scalar, …). The dropped
 * connection is oriented so edges always flow provides → accepts, regardless of
 * which end the user started from. Single-input nodes (a law, a measure) keep
 * only their newest incoming wire; the Verdict accepts many.
 */
import { addEdge, type Connection, type Edge } from '@xyflow/react'
import type { NodeKind, PlumbData } from './engine'

/** Look up a node's PlumbData by id (wraps ReactFlow's getNode). */
export type GetNodeData = (id: string) => PlumbData | undefined

/** Target kinds that hold at most one incoming wire. */
export const SINGLE_INPUT_KINDS: ReadonlySet<NodeKind> = new Set<NodeKind>(['measure', 'law'])

/** True when `src` provides a port type that `tgt` accepts. */
function typeOk(src?: PlumbData, tgt?: PlumbData): boolean {
  const provides = src?.provides
  const accepts = tgt?.accepts
  return !!provides && !!accepts && accepts.includes(provides)
}

/**
 * Valid if EITHER orientation type-checks — so the user can drag a wire in
 * either direction and still get a sensible connection. Used by
 * `isValidConnection` to light up compatible targets during the drag.
 */
export function canConnect(conn: Connection | Edge, getData: GetNodeData): boolean {
  if (!conn.source || !conn.target || conn.source === conn.target) return false
  const a = getData(conn.source)
  const b = getData(conn.target)
  return typeOk(a, b) || typeOk(b, a)
}

/** Orient a dropped connection so it flows provides → accepts (or null if invalid). */
export function orientConnection(conn: Connection, getData: GetNodeData): Connection | null {
  if (!conn.source || !conn.target || conn.source === conn.target) return null
  const a = getData(conn.source)
  const b = getData(conn.target)
  if (typeOk(a, b)) return { source: conn.source, target: conn.target, sourceHandle: null, targetHandle: null }
  if (typeOk(b, a)) return { source: conn.target, target: conn.source, sourceHandle: null, targetHandle: null }
  return null
}

/**
 * Apply a dropped connection to the edge list: orient it, enforce single-input
 * targets, and append. Returns the original list unchanged if the drop was invalid.
 */
export function connect(edges: Edge[], conn: Connection, getData: GetNodeData): Edge[] {
  const oriented = orientConnection(conn, getData)
  if (!oriented || !oriented.target) return edges

  const targetKind = getData(oriented.target)?.kind
  const base =
    targetKind && SINGLE_INPUT_KINDS.has(targetKind)
      ? edges.filter((e) => e.target !== oriented.target)
      : edges

  return addEdge({ ...oriented, animated: true }, base)
}
