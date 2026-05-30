import type { Node } from '@xyflow/react'
import type { NodeResult, PlumbData, PortType } from '../lib/engine'
import { STATUS_COLOR, PORT_COLOR, KIND_LABEL } from '../lib/theme'

function PortChip({ t }: { t: PortType }) {
  return (
    <span className="port-chip" style={{ background: `${PORT_COLOR[t]}22`, color: PORT_COLOR[t] }}>
      {t}
    </span>
  )
}

/**
 * The right-hand inspector: shows the selected node's identity, typed ports,
 * what feeds it, and its live evaluation. Empty state prompts a selection.
 */
export default function Inspector({
  node,
  result,
  incoming,
}: {
  node: Node<PlumbData> | null
  result?: NodeResult
  incoming: { label: string; type?: PortType }[]
}) {
  if (!node) {
    return (
      <aside className="inspector">
        <div className="inspector-empty">Select a node to inspect its data.</div>
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
              {status ? status.toUpperCase() : '—'}
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

      <div className="inspector-foot">id · {node.id}</div>
    </aside>
  )
}
