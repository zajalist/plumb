import { createContext, useCallback, useContext, useMemo, useState } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  ConnectionMode,
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
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import {
  evaluateGraph,
  type NodeResult,
  type PlumbData,
  type SceneState,
} from '../lib/engine'
import { DEF_BY_OP, nextId, seedGraph, specToNode } from '../lib/catalog'
import { STATUS_COLOR, STATUS_LABEL, PORT_COLOR } from '../lib/theme'
import { canConnect, connect, type GetNodeData } from '../lib/connection'
import Inspector from './Inspector'

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

export default function ConstraintGraph({
  scene,
  setBronzeX,
}: {
  scene: SceneState
  setBronzeX: (x: number) => void
}) {
  const [nodes, setNodes, onNodesChange] = useNodesState(SEED.nodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(SEED.edges)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const { screenToFlowPosition, getNode } = useReactFlow()

  // Live recompute whenever structure, wiring, or the scene knob changes.
  const results = useMemo(
    () => evaluateGraph(nodes, edges, scene, DEF_BY_OP),
    [nodes, edges, scene],
  )

  const onSelectionChange = useCallback(
    (p: OnSelectionChangeParams) => setSelectedId(p.nodes[0]?.id ?? null),
    [],
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
    (c: Connection) => setEdges((eds) => connect(eds, c, getData)),
    [setEdges, getData],
  )

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
  }, [])

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      const op = e.dataTransfer.getData('application/plumb-node')
      const spec = DEF_BY_OP[op]
      if (!spec) return
      const position = screenToFlowPosition({ x: e.clientX, y: e.clientY })
      setNodes((nds) => nds.concat(specToNode(spec, nextId(op), position)))
    },
    [screenToFlowPosition, setNodes],
  )

  const onDelete = useCallback(
    (id: string) => {
      setNodes((nds) => nds.filter((n) => n.id !== id))
      setEdges((eds) => eds.filter((e) => e.source !== id && e.target !== id))
      setSelectedId(null)
    },
    [setNodes, setEdges],
  )

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
            onSelectionChange={onSelectionChange}
            isValidConnection={isValidConnection}
            connectionMode={ConnectionMode.Strict}
            connectionRadius={50}
            nodeTypes={nodeTypes}
            deleteKeyCode={['Backspace', 'Delete']}
            fitView
            fitViewOptions={{ padding: 0.12 }}
            proOptions={{ hideAttribution: true }}
          >
            <Background color="#2a2f36" gap={24} />
            <Controls showInteractive={false} />
          </ReactFlow>
        </div>
        <Inspector
          node={selectedNode}
          result={selectedId ? results.get(selectedId) : undefined}
          incoming={incoming}
          bronzeX={scene.bronzeX}
          setBronzeX={setBronzeX}
          onDelete={onDelete}
        />
      </div>
    </ResultsContext.Provider>
  )
}
