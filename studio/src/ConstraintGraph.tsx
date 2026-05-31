import { useMemo } from 'react'
import {
  ReactFlow,
  Background,
  Handle,
  Position,
  type Node,
  type Edge,
  type NodeProps,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import type { Attempt, Gate } from './verdicts'

// ── status → colour (the gate grammar from spec §10.2) ──────────────────────
const PASS = '#28c850'
const FAIL = '#dc3232'
const SOFT = '#ebaa00'
const IDLE = '#5a5f66'

type GateStatus = 'pass' | 'fail' | 'soft' | 'skip'

function gateStatus(g: Gate | undefined, softCost: number): GateStatus {
  if (!g || g.skipped || g.ok === null) return 'skip'
  if (g.ok === false) return 'fail'
  // A passing gate still reads amber if a meaningful soft cost rode along.
  if (g.gate === 'constraints' && softCost > 1.0) return 'soft'
  return 'pass'
}

const STATUS_COLOR: Record<GateStatus, string> = {
  pass: PASS,
  fail: FAIL,
  soft: SOFT,
  skip: IDLE,
}

const STATUS_LABEL: Record<GateStatus, string> = {
  pass: 'PASS',
  fail: 'FAIL',
  soft: 'SOFT',
  skip: 'IDLE',
}

// ── custom node renderers ───────────────────────────────────────────────────
type OpData = { label: string; sub?: string }

function OpNode({ data }: NodeProps<Node<OpData>>) {
  return (
    <div className="node node-op">
      <Handle type="target" position={Position.Left} />
      <div className="node-title">{data.label}</div>
      {data.sub && <div className="node-sub">{data.sub}</div>}
      <Handle type="source" position={Position.Right} />
    </div>
  )
}

type GateData = {
  label: string
  status: GateStatus
  headline?: string
  detail?: string
}

function GateNode({ data }: NodeProps<Node<GateData>>) {
  const color = STATUS_COLOR[data.status]
  return (
    <div
      className="node node-gate"
      style={{ borderColor: color, boxShadow: `0 0 0 1px ${color}55` }}
    >
      <Handle type="target" position={Position.Left} />
      <div className="node-gate-head">
        <span className="node-title">{data.label}</span>
        <span className="pill" style={{ background: color }}>
          {STATUS_LABEL[data.status]}
        </span>
      </div>
      {data.headline && (
        <div className="node-headline" style={{ color }}>
          {data.headline}
        </div>
      )}
      {data.detail && <div className="node-sub">{data.detail}</div>}
      <Handle type="source" position={Position.Right} />
    </div>
  )
}

const nodeTypes = { op: OpNode, gate: GateNode }

// ── the Gallery graph (spec §9.4) ───────────────────────────────────────────
// Columns: selectors → operators → gate sinks → commit.
const COL = { sel: 0, op: 280, gate: 600, commit: 900 }

export default function ConstraintGraph({ attempt }: { attempt: Attempt }) {
  const byGate = useMemo(() => {
    const m = new Map<string, Gate>()
    for (const g of attempt.gates) m.set(g.gate, g)
    return m
  }, [attempt])

  const fmtCm = (m: number | null) =>
    m === null ? undefined : `${m >= 0 ? '+' : ''}${(m * 100).toFixed(1)} cm`

  const nodes: Node[] = useMemo(() => {
    const collision = gateStatus(byGate.get('collision'), attempt.soft_cost)
    const stability = gateStatus(byGate.get('stability'), attempt.soft_cost)
    const constraints = gateStatus(byGate.get('constraints'), attempt.soft_cost)
    const reach = gateStatus(byGate.get('reach'), attempt.soft_cost)

    const sG = byGate.get('stability')
    const cG = byGate.get('collision')
    const rG = byGate.get('reach')

    return [
      // selectors / inputs
      { id: 'bronze', type: 'op', position: { x: COL.sel, y: 60 }, data: { label: 'bronze_figure_03', sub: 'byId · top-heavy' } },
      { id: 'pedestal', type: 'op', position: { x: COL.sel, y: 150 }, data: { label: 'pedestal', sub: 'onSurface' } },
      { id: 'door', type: 'op', position: { x: COL.sel, y: 240 }, data: { label: 'oak_door', sub: 'articulated · swept' } },
      { id: 'walkway', type: 'op', position: { x: COL.sel, y: 330 }, data: { label: 'walkway', sub: 'navmesh r=0.45m' } },

      // operators (one per law)
      { id: 'clearance', type: 'op', position: { x: COL.op, y: 105 }, data: { label: 'convex clearance', sub: 'CoACD parts' } },
      { id: 'com', type: 'op', position: { x: COL.op, y: 60 }, data: { label: 'comOverFootprint', sub: 'margin ≥ 2cm' } },
      { id: 'keepclear', type: 'op', position: { x: COL.op, y: 240 }, data: { label: 'keep_clear(swept)', sub: 'door arc' } },
      { id: 'pathclear', type: 'op', position: { x: COL.op, y: 330 }, data: { label: 'path_clear', sub: '≥ 90cm' } },

      // gate sinks
      { id: 'g_collision', type: 'gate', position: { x: COL.gate, y: 30 }, data: { label: 'Collision', status: collision, headline: cG ? fmtCm(cG.value_m) : undefined } },
      { id: 'g_stability', type: 'gate', position: { x: COL.gate, y: 130 }, data: { label: 'Stability', status: stability, headline: sG ? fmtCm(sG.value_m) : undefined, detail: sG?.detail ?? undefined } },
      { id: 'g_constraints', type: 'gate', position: { x: COL.gate, y: 240 }, data: { label: 'Constraints', status: constraints } },
      { id: 'g_reach', type: 'gate', position: { x: COL.gate, y: 340 }, data: { label: 'Reach', status: reach, headline: rG && !rG.skipped ? fmtCm(rG.value_m) : undefined } },

      // commit
      {
        id: 'commit',
        type: 'gate',
        position: { x: COL.commit, y: 185 },
        data: {
          label: 'Commit',
          status: attempt.committed ? 'pass' : attempt.ok ? 'pass' : 'skip',
          detail: attempt.committed ? 'dispatched to UE5' : 'blocked',
        },
      },
    ]
  }, [byGate, attempt])

  const edges: Edge[] = useMemo(() => {
    const e = (id: string, source: string, target: string): Edge => ({
      id,
      source,
      target,
      animated: true,
    })
    return [
      e('e1', 'bronze', 'com'),
      e('e2', 'bronze', 'clearance'),
      e('e3', 'pedestal', 'clearance'),
      e('e4', 'door', 'keepclear'),
      e('e5', 'walkway', 'pathclear'),
      e('e6', 'clearance', 'g_collision'),
      e('e7', 'com', 'g_stability'),
      e('e8', 'keepclear', 'g_constraints'),
      e('e9', 'pathclear', 'g_reach'),
      // gate stack order (halt on first hard fail)
      e('s1', 'g_collision', 'g_stability'),
      e('s2', 'g_stability', 'g_constraints'),
      e('s3', 'g_constraints', 'g_reach'),
      e('s4', 'g_reach', 'commit'),
    ]
  }, [])

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      fitView
      fitViewOptions={{ padding: 0.15 }}
      proOptions={{ hideAttribution: true }}
      nodesDraggable
      nodesConnectable={false}
      elementsSelectable={false}
    >
      <Background color="#2a2f36" gap={24} />
    </ReactFlow>
  )
}
