// MaskRail — the UE4 Details-panel styled mask picker (design 2026-05-31).
// One surface mask (radio semantics) recolours the mesh; overlays (eye toggles) stack.
// Presentational: the parent (Viewport) owns state, computes on activate, and gates
// availability. Auto-compute shows a thin per-row progress bar (no spinner).
import { useState } from 'react'
import { Icon } from './Icons'
import type { Mask, MaskProviderMeta } from './masks'

const TEXTURED: MaskProviderMeta = {
  key: 'textured', name: 'textured', source: 'geometry', category: 'material',
  archetype: 'categorical', role: 'surface', needs_images: false, available: true,
}

type Props = {
  catalog: MaskProviderMeta[]
  masks: Mask[]
  surface: string
  overlays: Set<string>
  computing: Set<string>
  errors: Record<string, string>
  onSurface: (key: string) => void
  onOverlay: (key: string) => void
}

function pill(source: string): string {
  return source === 'hf' ? 'hf' : source === 'gemini' ? 'gem' : source === 'mcp' ? 'mcp' : 'geo'
}

function Row({ p, active, computing, error, onClick }: {
  p: MaskProviderMeta; active: boolean; computing: boolean; error?: string; onClick: () => void
}) {
  const disabled = !p.available
  const eye = active ? 'eye' : 'eye-off'
  return (
    <div className={`mrow${active ? ' sel' : ''}${disabled ? ' dis' : ''}`}
         onClick={disabled ? undefined : onClick}
         title={disabled ? `unavailable — set ${p.source.toUpperCase()} key` : p.name}>
      <Icon name={eye} className={`mrow-eye${active ? ' on' : ''}`} />
      <span className="mrow-name">{p.name}</span>
      {error
        ? <span className="mrow-err">{error}</span>
        : disabled
          ? <span className="mrow-err soft">no {p.source} key</span>
          : <span className={`mpill ${pill(p.source)}`}>{p.source === 'geometry' ? 'geo' : p.source}</span>}
      {computing && <span className="mrow-bar" />}
    </div>
  )
}

export function MaskRail({ catalog, surface, overlays, computing, errors, onSurface, onOverlay }: Props) {
  const [q, setQ] = useState('')
  const match = (p: MaskProviderMeta) => p.name.toLowerCase().includes(q.toLowerCase())

  const surfaces = [TEXTURED, ...catalog.filter((p) => p.role === 'surface')].filter(match)
  const ovs = catalog.filter((p) => p.role === 'overlay').filter(match)
  const activeOverlays = ovs.filter((p) => overlays.has(p.key)).length

  return (
    <div className="mrail">
      <div className="mrail-top">
        <Icon name="search" />
        <input className="mrail-search" placeholder="Filter masks…" value={q}
               onChange={(e) => setQ(e.target.value)} />
      </div>

      <div className="mrail-cat"><Icon name="caret" />Surface<span className="cnt">{surface} · {surfaces.length}</span></div>
      {surfaces.map((p) => (
        <Row key={p.key} p={p} active={surface === p.key} computing={computing.has(p.key)}
             error={errors[p.key]} onClick={() => onSurface(p.key)} />
      ))}

      <div className="mrail-cat"><Icon name="caret" />Overlays<span className="cnt">{activeOverlays} · {ovs.length}</span></div>
      {ovs.map((p) => (
        <Row key={p.key} p={p} active={overlays.has(p.key)} computing={computing.has(p.key)}
             error={errors[p.key]} onClick={() => onOverlay(p.key)} />
      ))}

      <div className="mrail-add"><Icon name="plus" />Add mask…</div>
    </div>
  )
}
