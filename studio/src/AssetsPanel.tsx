import { Icon } from './Icons'
import type { PAP } from './api'

export type Asset = {
  id: string
  name: string
  file: File
  pap?: PAP
  status: 'baking' | 'ok' | 'error'
  error?: string
}

export function AssetsPanel({ assets, selected, onSelect, onImport }: {
  assets: Asset[]
  selected: string | null
  onSelect: (id: string) => void
  onImport: (f: File) => void
}) {
  return (
    <section className="pane assets">
      <header>
        <div className="t"><Icon name="aperture" /><span>Assets</span></div>
        <span className="mono" style={{ fontSize: 10, color: 'var(--ink4)' }}>{assets.length}</span>
      </header>
      <div className="body">
        <div className="assetlist">
          {assets.map((a) => (
            <div key={a.id} className={`asset${a.id === selected ? ' sel' : ''}`} onClick={() => onSelect(a.id)}>
              <div className="thumb"><Icon name="aperture" /></div>
              <div className="meta">
                <div className="nm">{a.name}</div>
                <div className="sub">
                  {a.status === 'baking' ? 'baking…'
                    : a.status === 'error' ? <span style={{ color: 'var(--fail)' }}>bake failed</span>
                    : a.pap ? `${a.pap.semantics.cls} · ${a.pap.physical.mass_kg.toFixed(1)}kg`
                    : ''}
                </div>
              </div>
            </div>
          ))}
          <label className="dropzone">
            <Icon name="import" />
            <div className="dz">Drop a mesh to bake</div>
            <div className="dz2">.obj · .glb · .stl</div>
            <input
              type="file"
              accept=".obj,.glb,.stl"
              style={{ display: 'none' }}
              onChange={(e) => { const f = e.target.files?.[0]; if (f) onImport(f) }}
            />
          </label>
        </div>
      </div>
    </section>
  )
}
