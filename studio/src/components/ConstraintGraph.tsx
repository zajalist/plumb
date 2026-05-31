import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  ConnectionMode,
  PanOnScrollMode,
  SelectionMode,
  Handle,
  Position,
  useNodesState,
  useEdgesState,
  useReactFlow,
  type Node,
  type Edge,
  type Connection,
  type NodeProps,
  type OnSelectionChangeParams,
  type FinalConnectionState,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import {
  cm,
  evaluateGraph,
  type GateStatus,
  type NodeKind,
  type NodeOp,
  type NodeResult,
  type PlumbData,
  type PortType,
  type SceneState,
} from '../lib/engine'
import {
  DEF_BY_OP,
  DEFAULT_OP_BY_KIND,
  OPS_BY_KIND,
  nextId,
  profileGraphFor,
  seedGraph,
  specToNode,
} from '../lib/catalog'
import type { GateName, Verdict } from '../api'
import { STATUS_COLOR, STATUS_LABEL, PORT_COLOR } from '../lib/theme'
import { canConnect, connect, type GetNodeData } from '../lib/connection'
import { useUndoRedo } from '../lib/useUndoRedo'
import Inspector, { type EdgeInfo } from './Inspector'

// ── context so node renderers read live results ───────────────────────────────
const ResultsContext = createContext<Map<string, NodeResult>>(new Map())

function Ports({ data }: { data: PlumbData }) {
  return (
    <>
      {data.accepts?.length ? (
        <Handle
          type="target"
          position={Position.Left}
          style={{ background: PORT_COLOR[data.accepts[0]] }}
        />
      ) : null}
      {data.provides ? (
        <Handle
          type="source"
          position={Position.Right}
          style={{ background: PORT_COLOR[data.provides] }}
        />
      ) : null}
    </>
  )
}

// ── node renderers ────────────────────────────────────────────────────────────
function AssetNode({ data }: NodeProps<Node<PlumbData>>) {
  return (
    <div className="node node-asset">
      <div className="node-title">{data.label}</div>
      {data.sub && <div className="node-sub">{data.sub}</div>}
      <Ports data={data} />
    </div>
  )
}

function MeasureNode({ id, data }: NodeProps<Node<PlumbData>>) {
  const res = useContext(ResultsContext).get(id)
  return (
    <div className="node node-measure">
      <div className="node-title">{data.label}</div>
      {data.sub && <div className="node-sub">{data.sub}</div>}
      {res?.headline && <div className="node-measure-val">{res.headline}</div>}
      <Ports data={data} />
    </div>
  )
}

function LawNode({ id, data }: NodeProps<Node<PlumbData>>) {
  const res = useContext(ResultsContext).get(id)
  const status = res?.status ?? 'idle'
  const color = STATUS_COLOR[status]
  return (
    <div
      className="node node-law"
      style={{ borderColor: color, boxShadow: `0 0 0 1px ${color}55` }}
    >
      <div className="node-gate-head">
        <span className="node-title">
          {data.label}
          {data.hard === false && <span className="soft-tag"> soft</span>}
        </span>
        <span className="pill" style={{ background: color }}>
          {STATUS_LABEL[status]}
        </span>
      </div>
      <div className="node-sub">{data.sub}</div>
      {res?.headline && (
        <div className="node-headline" style={{ color }}>
          {res.headline}
        </div>
      )}
      {res?.detail && <div className="node-sub">{res.detail}</div>}
      <Ports data={data} />
    </div>
  )
}

function FieldNode({ data }: NodeProps<Node<PlumbData>>) {
  return (
    <div className="node node-field">
      <div className="node-title">{data.label}</div>
      {data.sub && <div className="node-sub">{data.sub}</div>}
      <Ports data={data} />
    </div>
  )
}

function VerdictNode({ id, data }: NodeProps<Node<PlumbData>>) {
  const res = useContext(ResultsContext).get(id)
  const status = res?.status ?? 'idle'
  const color = STATUS_COLOR[status]
  return (
    <div
      className="node node-verdict"
      style={{ borderColor: color, boxShadow: `0 0 0 1px ${color}55` }}
    >
      <div className="node-gate-head">
        <span className="node-title">{data.label}</span>
        <span className="pill" style={{ background: color }}>
          {status === 'pass' ? 'COMMIT' : status === 'fail' ? 'BLOCKED' : 'IDLE'}
        </span>
      </div>
      {res?.detail && <div className="node-sub">{res.detail}</div>}
      <Ports data={data} />
    </div>
  )
}

const nodeTypes = {
  asset: AssetNode,
  measure: MeasureNode,
  law: LawNode,
  field: FieldNode,
  verdict: VerdictNode,
}

const SEED = seedGraph()

/** A baked asset offered to Object nodes (the P1 sync list) + its baked facts (P2). */
export type ObjectOption = {
  id: string
  label: string
  sub?: string
  mass?: number
  com?: number[]
  /** Bake archetype (e.g. 'door') — drives profile auto-graphs. */
  profile?: string
}

// ── Invalid-connection feedback ───────────────────────────────────────────────
/** Law labels whose entry port accepts a given carried type (for the reject hint). */
const lawsAccepting = (t: PortType): string[] =>
  OPS_BY_KIND.law.filter((l) => l.accepts?.includes(t)).map((l) => l.label)

/**
 * Why a `src → tgt` wire was rejected, phrased as a fix. Returns null when the
 * pair is actually compatible (so the caller can try the other drag direction).
 * The type system stays strict — this only explains the block (SYNC: keep strict,
 * improve feedback).
 */
function rejectHint(src?: PlumbData, tgt?: PlumbData): string | null {
  if (!src || !tgt || src === tgt) return null
  const provides = src.provides
  if (!provides) return null
  if (tgt.kind === 'verdict') {
    if (tgt.accepts?.includes(provides)) return null
    return `Verdict only accepts a Law’s output — wire ${src.label} into a Law first.`
  }
  const accepts = tgt.accepts
  if (!accepts) return null // tgt takes no input; let the other direction explain
  if (accepts.includes(provides)) return null // actually valid
  const fixes = tgt.kind === 'law' ? lawsAccepting(provides) : []
  const suggestion = fixes.length
    ? ` Wire it into a Law that accepts ${provides} — try ${fixes.join(' or ')}.`
    : ''
  return `${src.label} outputs a ${provides}; ${tgt.label} accepts ${accepts.join('/')}.${suggestion}`
}

// P4: which backend gate drives each law / measure op, so a real Verdict lights
// up the graph (spec §11 — the node editor as the "intent conscience").
const LAW_GATE: Partial<Record<NodeOp, GateName>> = {
  stable: 'stability', noClip: 'collision', walkwayClear: 'reach',
  facing: 'constraints', doorClear: 'constraints',
}
const MEASURE_GATE: Partial<Record<NodeOp, GateName>> = {
  comOverFootprint: 'stability', clearance: 'collision', pathWidth: 'reach',
}

export default function ConstraintGraph({
  scene,
  objects = [],
  verdict = null,
}: {
  scene: SceneState
  objects?: ObjectOption[]
  verdict?: Verdict | null
}) {
  const [nodes, setNodes, onNodesChange] = useNodesState(SEED.nodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(SEED.edges)
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null)
  const { screenToFlowPosition, getNode } = useReactFlow()
  const { takeSnapshot, undo, redo } = useUndoRedo()

  // Transient canvas hint shown when a wire is rejected (auto-dismisses).
  const [toast, setToast] = useState<string | null>(null)
  const toastTimer = useRef<number | null>(null)
  const showToast = useCallback((msg: string) => {
    setToast(msg)
    if (toastTimer.current) window.clearTimeout(toastTimer.current)
    toastTimer.current = window.setTimeout(() => setToast(null), 4000)
  }, [])
  useEffect(() => () => { if (toastTimer.current) window.clearTimeout(toastTimer.current) }, [])

  // Assets whose profile subgraph we've already auto-spawned — so we never
  // duplicate, and never fight the user by re-adding after they delete it.
  const materialized = useRef<Set<string>>(new Set())

  // Live recompute whenever structure, wiring, or the scene knob changes. When a
  // real backend Verdict is present, overlay its gate truth onto the matching
  // measure/law/verdict nodes (P4) — otherwise engine.ts drives the demo knob.
  const results = useMemo(() => {
    const base = evaluateGraph(nodes, edges, scene, DEF_BY_OP)
    if (!verdict) return base
    const gateBy = new Map(verdict.gates.map((g) => [g.gate, g]))
    for (const n of nodes) {
      const d = n.data as PlumbData
      if (d.kind === 'measure') {
        const g = MEASURE_GATE[d.op] && gateBy.get(MEASURE_GATE[d.op]!)
        if (g && g.value_m != null) base.set(n.id, { status: 'idle', headline: cm(g.value_m) })
      } else if (d.kind === 'law') {
        const g = LAW_GATE[d.op] && gateBy.get(LAW_GATE[d.op]!)
        if (g) {
          const status: GateStatus =
            g.ok === false ? (d.hard === false ? 'soft' : 'fail') : g.ok === true ? 'pass' : 'idle'
          base.set(n.id, {
            status,
            headline: g.value_m != null ? cm(g.value_m) : undefined,
            detail: g.detail ?? undefined,
          })
        }
      } else if (d.kind === 'verdict') {
        base.set(
          n.id,
          verdict.ok
            ? { status: 'pass', detail: 'all gates pass · commit' }
            : { status: 'fail', detail: `blocked at ${verdict.stopped_at ?? '—'}` },
        )
      }
    }
    return base
  }, [nodes, edges, scene, verdict])

  // Profile auto-graphs: when a baked asset with a known profile (today: a door)
  // first appears in the sync list, wire its "sentence" for the user. Otherwise
  // the canvas stays empty (SYNC: empty unless a specific profile).
  useEffect(() => {
    const fresh = objects.filter(
      (o) => profileGraphFor(o.profile) && !materialized.current.has(o.id),
    )
    if (fresh.length === 0) return
    let row = materialized.current.size
    const addNodes: Node[] = []
    const addEdges: Edge[] = []
    for (const o of fresh) {
      const build = profileGraphFor(o.profile)!
      const g = build(o.id, o.label, { x: 40, y: 40 + row * 200 })
      addNodes.push(...g.nodes)
      addEdges.push(...g.edges)
      materialized.current.add(o.id)
      row++
    }
    takeSnapshot()
    setNodes((nds) => nds.concat(addNodes))
    setEdges((eds) => eds.concat(addEdges))
  }, [objects, setNodes, setEdges, takeSnapshot])

  // Track the whole node selection (box-select can pick many); a wire selection
  // is mutually exclusive with nodes — the inspector shows one or the other.
  const onSelectionChange = useCallback((p: OnSelectionChangeParams) => {
    setSelectedIds(p.nodes.map((n) => n.id))
    setSelectedEdgeId(p.nodes.length ? null : p.edges[0]?.id ?? null)
  }, [])

  // A single-node selection drives the detailed inspector; multi-select is a list.
  const selectedId = selectedIds.length === 1 ? selectedIds[0] : null

  // The names/kinds of every selected node, for the multi-select panel.
  const selectedNodes = useMemo(
    () =>
      selectedIds.map((id) => {
        const d = nodes.find((n) => n.id === id)?.data as PlumbData | undefined
        return { id, label: d?.label ?? id, kind: d?.kind ?? ('asset' as const) }
      }),
    [selectedIds, nodes],
  )

  // The selected node + what feeds it, for the inspector.
  const selectedNode = (nodes.find((n) => n.id === selectedId) ?? null) as Node<PlumbData> | null
  const incoming = useMemo(
    () =>
      edges
        .filter((e) => e.target === selectedId)
        .map((e) => {
          const src = nodes.find((n) => n.id === e.source)
          const data = src?.data as PlumbData | undefined
          return { label: data?.label ?? e.source, type: data?.provides }
        }),
    [edges, nodes, selectedId],
  )

  // The selected wire, resolved to its endpoints + the port type it carries.
  const selectedEdge = useMemo<EdgeInfo | null>(() => {
    const e = edges.find((x) => x.id === selectedEdgeId)
    if (!e) return null
    const src = nodes.find((n) => n.id === e.source)?.data as PlumbData | undefined
    const tgt = nodes.find((n) => n.id === e.target)?.data as PlumbData | undefined
    return {
      id: e.id,
      source: { label: src?.label ?? e.source, kind: src?.kind ?? 'asset' },
      target: { label: tgt?.label ?? e.target, kind: tgt?.kind ?? 'asset' },
      type: src?.provides,
    }
  }, [edges, nodes, selectedEdgeId])

  // Shared accessor: a node's PlumbData by id, for the connection rules.
  const getData = useCallback<GetNodeData>(
    (id) => getNode(id)?.data as PlumbData | undefined,
    [getNode],
  )

  // Typed-port validity + dropped-connection handling live in lib/connection.ts.
  const isValidConnection = useCallback(
    (c: Connection | Edge) => canConnect(c, getData),
    [getData],
  )
  const onConnect = useCallback(
    (c: Connection) => {
      takeSnapshot()
      setEdges((eds) => connect(eds, c, getData))
    },
    [setEdges, getData, takeSnapshot],
  )

  // A wire dropped on an incompatible port makes no connection (strict typed
  // ports). React Flow swallows it silently — so explain the block + the fix.
  const onConnectEnd = useCallback(
    (_: MouseEvent | TouchEvent, state: FinalConnectionState) => {
      if (state.isValid) return // valid drops are handled by onConnect
      const from = (state.fromNode?.data ?? undefined) as PlumbData | undefined
      const to = (state.toNode?.data ?? undefined) as PlumbData | undefined
      if (!to) return // released on empty canvas — a cancel, not an error
      const msg = rejectHint(from, to) ?? rejectHint(to, from)
      if (msg) showToast(msg)
    },
    [showToast],
  )

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
  }, [])

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      // New (P0): an abstract node carries its kind → start at that kind's default
      // op. Legacy: a concrete op was dragged. Either resolves to a NodeDef.
      const kind = e.dataTransfer.getData('application/plumb-node-kind') as NodeKind | ''
      const op = kind ? DEFAULT_OP_BY_KIND[kind] : e.dataTransfer.getData('application/plumb-node')
      const spec = DEF_BY_OP[op]
      if (!spec) return
      takeSnapshot()
      const position = screenToFlowPosition({ x: e.clientX, y: e.clientY })
      setNodes((nds) => nds.concat(specToNode(spec, nextId(op), position)))
    },
    [screenToFlowPosition, setNodes, takeSnapshot],
  )

  // Change a node's concrete op (the inspector Type dropdown). Re-derives the
  // node's metadata from the registry and prunes any wire whose typed ports no
  // longer match (e.g. a measure switched scalar→bool drops its law edge).
  const onChangeOp = useCallback(
    (id: string, op: NodeOp) => {
      const def = DEF_BY_OP[op]
      if (!def) return
      takeSnapshot()
      setNodes((nds) =>
        nds.map((n) =>
          n.id === id
            ? {
                ...n,
                data: {
                  ...(n.data as PlumbData),
                  op: def.op, label: def.label, sub: def.sub,
                  accepts: def.accepts, provides: def.provides,
                  hard: def.hard, control: def.control, tol: def.tol,
                },
              }
            : n,
        ),
      )
      setEdges((eds) =>
        eds.filter((e) => {
          if (e.source !== id && e.target !== id) return true
          const provides = e.source === id ? def.provides : getData(e.source)?.provides
          const accepts = e.target === id ? def.accepts : getData(e.target)?.accepts
          return !!provides && !!accepts && accepts.includes(provides)
        }),
      )
    },
    [setNodes, setEdges, getData, takeSnapshot],
  )

  // Edit a law's tolerance (the inspector number field). Re-derives the node's
  // sub-label from its comparator + unit so the canvas reflects the new threshold.
  const onSetTol = useCallback(
    (id: string, tol: number) => {
      takeSnapshot()
      setNodes((nds) =>
        nds.map((n) => {
          if (n.id !== id) return n
          const d = n.data as PlumbData
          const def = DEF_BY_OP[d.op]
          const sub = def?.cmp && def?.tolUnit ? `${def.cmp} ${tol}${def.tolUnit}` : d.sub
          return { ...n, data: { ...d, tol, sub } }
        }),
      )
    },
    [setNodes, takeSnapshot],
  )

  // Toggle a law between hard (gates the commit) and soft (warns only).
  const onSetHard = useCallback(
    (id: string, hard: boolean) => {
      takeSnapshot()
      setNodes((nds) =>
        nds.map((n) => (n.id === id ? { ...n, data: { ...(n.data as PlumbData), hard } } : n)),
      )
    },
    [setNodes, takeSnapshot],
  )

  // Bind an Object node to a real imported/baked asset (the P1 sync). The node
  // becomes a generic `object` carrying the asset's id + baked label/facts.
  const onBindAsset = useCallback(
    (id: string, assetId: string, label: string, sub?: string) => {
      takeSnapshot()
      setNodes((nds) =>
        nds.map((n) =>
          n.id === id
            ? {
                ...n,
                data: {
                  ...(n.data as PlumbData),
                  op: 'object', assetId, label, sub,
                  provides: 'object', accepts: undefined, hard: undefined, control: undefined,
                },
              }
            : n,
        ),
      )
    },
    [setNodes, takeSnapshot],
  )

  // Delete a set of nodes (one or many) plus any wire touching them.
  const onDeleteNodes = useCallback(
    (ids: string[]) => {
      if (ids.length === 0) return
      takeSnapshot()
      const doomed = new Set(ids)
      setNodes((nds) => nds.filter((n) => !doomed.has(n.id)))
      setEdges((eds) => eds.filter((e) => !doomed.has(e.source) && !doomed.has(e.target)))
      setSelectedIds([])
    },
    [setNodes, setEdges, takeSnapshot],
  )
  const onDelete = useCallback((id: string) => onDeleteNodes([id]), [onDeleteNodes])

  const onDeleteEdge = useCallback(
    (id: string) => {
      takeSnapshot()
      setEdges((eds) => eds.filter((e) => e.id !== id))
      setSelectedEdgeId(null)
    },
    [setEdges, takeSnapshot],
  )

  // Snapshot once at the start of a drag (single or multi-selection), not every
  // tick, and before any keyboard/right-click deletion — so one undo reverses
  // one whole gesture.
  const onNodeDragStart = useCallback(() => takeSnapshot(), [takeSnapshot])
  const onBeforeDelete = useCallback(async () => {
    takeSnapshot()
    return true
  }, [takeSnapshot])

  // Ctrl/Cmd+Z undo, Ctrl+Y or Ctrl/Cmd+Shift+Z redo — skipped while typing.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey)) return
      const t = e.target as HTMLElement | null
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return
      const k = e.key.toLowerCase()
      if (k === 'z' && !e.shiftKey) {
        e.preventDefault()
        undo()
      } else if (k === 'y' || (k === 'z' && e.shiftKey)) {
        e.preventDefault()
        redo()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [undo, redo])

  return (
    <ResultsContext.Provider value={results}>
      <div className="graph-main">
        <div className="canvas" onDrop={onDrop} onDragOver={onDragOver}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onConnectEnd={onConnectEnd}
            onSelectionChange={onSelectionChange}
            onNodeDragStart={onNodeDragStart}
            onSelectionDragStart={onNodeDragStart}
            onBeforeDelete={onBeforeDelete}
            isValidConnection={isValidConnection}
            connectionMode={ConnectionMode.Strict}
            connectionRadius={50}
            nodeTypes={nodeTypes}
            deleteKeyCode={['Backspace', 'Delete']}
            panOnScroll
            panOnScrollMode={PanOnScrollMode.Free}
            zoomOnScroll={false}
            selectionOnDrag
            selectionMode={SelectionMode.Partial}
            panOnDrag={[1, 2]}
            fitView
            fitViewOptions={{ padding: 0.12 }}
            proOptions={{ hideAttribution: true }}
          >
            <Background color="#2a2f36" gap={24} />
            <Controls showInteractive={false} />
          </ReactFlow>
          {toast && (
            <div className="ne-toast" role="status">
              {toast}
            </div>
          )}
        </div>
        <Inspector
          node={selectedNode}
          edge={selectedEdge}
          selected={selectedNodes}
          result={selectedId ? results.get(selectedId) : undefined}
          incoming={incoming}
          objects={objects}
          onChangeOp={onChangeOp}
          onSetTol={onSetTol}
          onSetHard={onSetHard}
          onBindAsset={onBindAsset}
          onDelete={onDelete}
          onDeleteEdge={onDeleteEdge}
          onDeleteMany={onDeleteNodes}
        />
      </div>
    </ResultsContext.Provider>
  )
}
