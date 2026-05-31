/**
 * Undo/redo for the constraint canvas — a small history of {nodes, edges}
 * snapshots, kept out of the component so the time-travel logic is testable and
 * the editor stays declarative.
 *
 * The discipline: callers `takeSnapshot()` *before* a discrete mutation (a wire,
 * a drop, a delete, the first tick of a drag). Continuous events (every drag
 * tick, every selection) are NOT snapshotted, so one Ctrl+Z reverses one
 * intent — not one pixel of motion. `undo`/`redo` swap the live graph with a
 * stored snapshot and shuttle the displaced state onto the opposite stack.
 */
import { useCallback, useState } from 'react'
import { useReactFlow, type Edge, type Node } from '@xyflow/react'

type Snapshot = { nodes: Node[]; edges: Edge[] }

/** Cap the history so a long session can't grow the stacks without bound. */
const MAX_HISTORY = 100

export function useUndoRedo() {
  const { getNodes, getEdges, setNodes, setEdges } = useReactFlow()
  const [past, setPast] = useState<Snapshot[]>([])
  const [future, setFuture] = useState<Snapshot[]>([])

  /** Record the current graph as a restore point and drop any redo branch. */
  const takeSnapshot = useCallback(() => {
    setPast((p) => [...p, { nodes: getNodes(), edges: getEdges() }].slice(-MAX_HISTORY))
    setFuture([])
  }, [getNodes, getEdges])

  const undo = useCallback(() => {
    if (past.length === 0) return
    const prev = past[past.length - 1]
    setFuture((f) => [{ nodes: getNodes(), edges: getEdges() }, ...f])
    setPast(past.slice(0, -1))
    setNodes(prev.nodes)
    setEdges(prev.edges)
  }, [past, getNodes, getEdges, setNodes, setEdges])

  const redo = useCallback(() => {
    if (future.length === 0) return
    const next = future[0]
    setPast((p) => [...p, { nodes: getNodes(), edges: getEdges() }])
    setFuture(future.slice(1))
    setNodes(next.nodes)
    setEdges(next.edges)
  }, [future, getNodes, getEdges, setNodes, setEdges])

  return { takeSnapshot, undo, redo, canUndo: past.length > 0, canRedo: future.length > 0 }
}
