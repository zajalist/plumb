import type { Node } from '@xyflow/react'
import { BRONZE_X_MIN, BRONZE_X_MAX, type NodeKind, type NodeOp, type NodeResult, type PlumbData, type PortType } from '../lib/engine'
import { STATUS_COLOR, PORT_COLOR, KIND_LABEL } from '../lib/theme'
import { OPS_BY_KIND } from '../lib/catalog'

/** A selected wire, resolved to the endpoints + the port type it carries. */
export type EdgeInfo = {
  id: string
  source: { label: string; kind: NodeKind }
  target: { label: string; kind: NodeKind }
  type?: PortType
}

/** One entry in a multi-node selection (name + kind, for the list view). */
export type SelectedNode = { id: string; label: string; kind: NodeKind }

function PortChip({ t }: { t: PortType }) {
  return (
    <span className="port-chip" style={{ background: `${PORT_COLOR[t]}22`, color: PORT_COLOR[t] }}>
      {t}
    </span>
  )
}

/** The inspector for a selected wire: the two nodes it joins and its carried type. */
function EdgeInspector({ edge, onDelete }: { edge: EdgeInfo; onDelete: (id: string) => void }) {
  return (
    <aside className="inspector">
      <div className="inspector-kind">Wire · connection</div>
      <div className="inspector-title">
        {edge.source.label} → {edge.target.label}
      </div>

      <div className="inspector-section">
        <div className="inspector-h">Carries</div>
        <div className="inspector-row">
          <span className="inspector-key">type</span>
          <span>{edge.type ? <PortChip t={edge.type} /> : <em>untyped</em>}</span>
        </div>
      </div>

      <div className="inspector-section">
        <div className="inspector-h">Connects</div>
        <div className="inspector-row">
          <span className="inspector-key">from</span>
          <span>
            {edge.source.label} <em>· {KIND_LABEL[edge.source.kind] ?? edge.source.kind}</em>
          </span>
        </div>
        <div className="inspector-row">
          <span className="inspector-key">to</span>
          <span>
            {edge.target.label} <em>· {KIND_LABEL[edge.target.kind] ?? edge.target.kind}</em>
          </span>
        </div>
      </div>

      <div className="inspector-section">
        <button className="inspector-delete" onClick={() => onDelete(edge.id)}>
          Delete wire
        </button>
      </div>

      <div className="inspector-foot">id · {edge.id}</div>
    </aside>
  )
}

/** The inspector for a multi-node selection: the names + a bulk delete. */
function MultiInspector({
  selected,
  onDeleteMany,
}: {
  selected: SelectedNode[]
  onDeleteMany: (ids: string[]) => void
}) {
  return (
    <aside className="inspector">
      <div className="inspector-kind">Selection</div>
      <div className="inspector-title">{selected.length} nodes selected</div>

      <div className="inspector-section">
        <div className="inspector-h">Nodes</div>
        {selected.map((s) => (
          <div className="inspector-row" key={s.id}>
            <span>{s.label}</span>
            <em>{KIND_LABEL[s.kind] ?? s.kind}</em>
          </div>
        ))}
      </div>

      <div className="inspector-section">
        <button className="inspector-delete" onClick={() => onDeleteMany(selected.map((s) => s.id))}>
          Delete {selected.length} nodes
        </button>
      </div>
    </aside>
  )
}

/**
 * The right-hand inspector: shows the selected node's identity, typed ports,
 * what feeds it, and its live evaluation. With many nodes selected it lists
 * them; with a wire selected it describes the connection. Empty state prompts.
 */
export default function Inspector({
  node,
  edge,
  selected,
  result,
  incoming,
  bronzeX,
  setBronzeX,
  objects = [],
  onChangeOp,
  onBindAsset,
  onDelete,
  onDeleteEdge,
  onDeleteMany,
}: {
  node: Node<PlumbData> | null
  edge?: EdgeInfo | null
  selected?: SelectedNode[]
  result?: NodeResult
  incoming: { label: string; type?: PortType }[]
  bronzeX: number
  setBronzeX: (x: number) => void
  objects?: { id: string; label: string; sub?: string; mass?: number; com?: number[] }[]
  onChangeOp: (id: string, op: NodeOp) => void
  onBindAsset: (id: string, assetId: string, label: string, sub?: string) => void
  onDelete: (id: string) => void
  onDeleteEdge: (id: string) => void
  onDeleteMany: (ids: string[]) => void
}) {
  // Many nodes → list them; one node → details; a wire → connection; else prompt.
  if (selected && selected.length > 1) {
    return <MultiInspector selected={selected} onDeleteMany={onDeleteMany} />
  }
  if (!node) {
    if (edge) return <EdgeInspector edge={edge} onDelete={onDeleteEdge} />
    return (
      <aside className="inspector">
        <div className="inspector-empty">Select a node or wire to inspect it.</div>
      </aside>
    )
  }

  const d = node.data
  const status = result?.status
  return (
    <aside className="inspector">
      <div className="inspector-kind">{KIND_LABEL[d.kind] ?? d.kind}</div>
      <div className="inspector-title">{d.label}</div>
      {d.sub && <div className="inspector-sub">{d.sub}</div>}

      {d.kind === 'asset' ? (
        <div className="inspector-section">
          <div className="inspector-h">Object</div>
          <select
            className="inspector-select"
            value={d.assetId ? `asset:${d.assetId}` : `op:${d.op}`}
            onChange={(e) => {
              const v = e.target.value
              if (v.startsWith('asset:')) {
                const o = objects.find((x) => x.id === v.slice(6))
                if (o) onBindAsset(node.id, o.id, o.label, o.sub)
              } else {
                onChangeOp(node.id, v.slice(3) as NodeOp)
              }
            }}
          >
            {objects.length > 0 && (
              <optgroup label="Imported assets">
                {objects.map((o) => (
                  <option key={o.id} value={`asset:${o.id}`}>{o.label}</option>
                ))}
              </optgroup>
            )}
            <optgroup label="Demo assets">
              {OPS_BY_KIND.asset.map((o) => (
                <option key={o.op} value={`op:${o.op}`}>{o.label}</option>
              ))}
            </optgroup>
          </select>
          {objects.length === 0 && (
            <div className="inspector-detail">Import &amp; bake a mesh to bind a real object.</div>
          )}
        </div>
      ) : (
        OPS_BY_KIND[d.kind] && OPS_BY_KIND[d.kind].length > 1 && (
          <div className="inspector-section">
            <div className="inspector-h">Type</div>
            <select
              className="inspector-select"
              value={d.op}
              onChange={(e) => onChangeOp(node.id, e.target.value as NodeOp)}
            >
              {OPS_BY_KIND[d.kind].map((o) => (
                <option key={o.op} value={o.op}>{o.label}</option>
              ))}
            </select>
          </div>
        )
      )}

      {d.kind === 'asset' && d.assetId && (() => {
        const o = objects.find((x) => x.id === d.assetId)
        if (!o || (o.mass === undefined && !o.com)) return null
        return (
          <div className="inspector-section">
            <div className="inspector-h">Baked · PAP</div>
            {o.mass !== undefined && (
              <div className="inspector-row">
                <span className="inspector-key">mass</span>
                <span>{o.mass.toFixed(1)} kg</span>
              </div>
            )}
            {o.com && (
              <div className="inspector-row">
                <span className="inspector-key">centre of mass</span>
                <span>{o.com.map((n) => n.toFixed(2).replace(/^(-?)0\./, '$1.')).join(', ')}</span>
              </div>
            )}
          </div>
        )
      })()}

      <div className="inspector-section">
        <div className="inspector-h">Ports</div>
        <div className="inspector-row">
          <span className="inspector-key">in</span>
          <span>
            {d.accepts?.length ? d.accepts.map((t) => <PortChip key={t} t={t} />) : <em>none</em>}
          </span>
        </div>
        <div className="inspector-row">
          <span className="inspector-key">out</span>
          <span>{d.provides ? <PortChip t={d.provides} /> : <em>none</em>}</span>
        </div>
      </div>

      <div className="inspector-section">
        <div className="inspector-h">Inputs</div>
        {incoming.length ? (
          incoming.map((i, k) => (
            <div className="inspector-row" key={k}>
              <span>{i.label}</span>
              {i.type && <PortChip t={i.type} />}
            </div>
          ))
        ) : (
          <div className="inspector-row">
            <em>unwired</em>
          </div>
        )}
      </div>

      {(d.kind === 'law' || d.kind === 'measure' || d.kind === 'verdict') && (
        <div className="inspector-section">
          <div className="inspector-h">Evaluation</div>
          {d.kind === 'law' && (
            <div className="inspector-row">
              <span className="inspector-key">type</span>
              <span>{d.hard === false ? 'soft (warns)' : 'hard (gates commit)'}</span>
            </div>
          )}
          {d.sub && d.kind === 'law' && (
            <div className="inspector-row">
              <span className="inspector-key">tolerance</span>
              <span>{d.sub}</span>
            </div>
          )}
          <div className="inspector-row">
            <span className="inspector-key">status</span>
            <span style={{ color: status ? STATUS_COLOR[status] : undefined, fontWeight: 700 }}>
              {status ? status.toUpperCase() : 'IDLE'}
            </span>
          </div>
          {result?.headline && (
            <div className="inspector-row">
              <span className="inspector-key">value</span>
              <span style={{ color: status ? STATUS_COLOR[status] : undefined }}>
                {result.headline}
              </span>
            </div>
          )}
          {result?.detail && <div className="inspector-detail">{result.detail}</div>}
        </div>
      )}

      {d.control === 'bronzeX' && (
        <div className="inspector-section">
          <div className="inspector-h">Control · x-offset</div>
          <input
            className="knob"
            type="range"
            min={BRONZE_X_MIN}
            max={BRONZE_X_MAX}
            step={0.002}
            value={bronzeX}
            onChange={(e) => setBronzeX(parseFloat(e.target.value))}
          />
          <div className="knob-val">x +{(bronzeX * 100).toFixed(1)}cm</div>
        </div>
      )}

      <div className="inspector-section">
        <button className="inspector-delete" onClick={() => onDelete(node.id)}>
          Delete node
        </button>
      </div>

      <div className="inspector-foot">id · {node.id}</div>
    </aside>
  )
}
