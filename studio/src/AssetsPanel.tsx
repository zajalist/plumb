import { useState } from 'react'
import { Icon } from './Icons'
import type { PAP, WdfAsset } from './api'

export type Asset = {
  id: string
  name: string
  file?: File            // absent for assets declared by an opened .wdf
  extras?: File[]        // sidecars (.bin/textures) so the viewport can render a .gltf
  pap?: PAP
  status: 'queued' | 'converting' | 'baking' | 'ok' | 'error' | 'declared'
  error?: string
  wdf?: WdfAsset         // present when this asset came from a .wdf vocabulary
  folder?: string        // organisational folder (optional)
  color?: string         // user colour-code (optional)
}

const COLORS = ['#34C0AD', '#D9A84C', '#E0694F', '#5C8BD6', '#A088B0', '#6FBF73', '#7C8AA0']

function statusText(a: Asset) {
  if (a.status === 'baking') return 'baking…'
  if (a.status === 'converting') return 'converting…'
  if (a.status === 'queued') return 'queued…'
  if (a.status === 'error') return <span style={{ color: 'var(--fail)' }}>bake failed</span>
  if (a.status === 'declared' && a.wdf) return `${a.wdf.profile ?? 'asset'} · ${Object.keys(a.wdf.material).length} masks`
  if (a.pap) return `${a.pap.semantics.cls} · ${a.pap.physical.mass_kg.toFixed(1)}kg`
  return ''
}

export function AssetsPanel({ assets, selected, onSelect, onImport, onDelete, onUpdate }: {
  assets: Asset[]
  selected: string | null
  onSelect: (id: string) => void
  onImport: (f: File) => void
  onDelete?: (id: string) => void
  onUpdate?: (id: string, patch: Partial<Asset>) => void
}) {
  const [menu, setMenu] = useState<string | null>(null)
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({})
  const [naming, setNaming] = useState(false)   // inline "new folder" input open
  const [folderName, setFolderName] = useState('')
  const closeMenu = () => { setMenu(null); setNaming(false); setFolderName('') }

  const folders = [...new Set(assets.map((a) => a.folder).filter(Boolean))] as string[]
  const groupOf = (f: string) => assets.filter((a) => a.folder === f)
  const ungrouped = assets.filter((a) => !a.folder)
  const canEdit = !!(onDelete || onUpdate)

  const renderAsset = (a: Asset) => (
    <div key={a.id} className={`asset${a.id === selected ? ' sel' : ''}`} onClick={() => onSelect(a.id)}>
      <div className="thumb" style={a.color ? { borderColor: a.color, boxShadow: `inset 0 0 0 1px ${a.color}` } : undefined}>
        <Icon name="aperture" />
      </div>
      <div className="meta">
        <div className="nm">{a.name}</div>
        <div className="sub">{statusText(a)}</div>
      </div>
      {canEdit && (
        <button className="asset-menu-btn" title="Organise"
          onClick={(e) => { e.stopPropagation(); setMenu(menu === a.id ? null : a.id); setNaming(false) }}>⋯</button>
      )}
      {menu === a.id && (
        <div className="asset-menu" onClick={(e) => e.stopPropagation()}>
          {onUpdate && (
            <div className="am-colors">
              {COLORS.map((c) => (
                <button key={c} style={{ background: c }} className={a.color === c ? 'on' : ''}
                  onClick={() => { onUpdate(a.id, { color: a.color === c ? undefined : c }); closeMenu() }} />
              ))}
            </div>
          )}
          {naming ? (
            <input className="am-input" autoFocus placeholder="Folder name…" value={folderName}
              onChange={(e) => setFolderName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && folderName.trim()) { onUpdate?.(a.id, { folder: folderName.trim() }); closeMenu() }
                else if (e.key === 'Escape') { setNaming(false); setFolderName('') }
              }} />
          ) : (
            <>
              {onUpdate && folders.filter((f) => f !== a.folder).map((f) => (
                <button className="am-item" key={f} onClick={() => { onUpdate(a.id, { folder: f }); closeMenu() }}>
                  Move to “{f}”
                </button>
              ))}
              {onUpdate && <button className="am-item" onClick={() => setNaming(true)}>New folder…</button>}
              {onUpdate && a.folder && (
                <button className="am-item" onClick={() => { onUpdate(a.id, { folder: undefined }); closeMenu() }}>
                  Remove from folder
                </button>
              )}
              {onDelete && <button className="am-item danger" onClick={() => { onDelete(a.id); closeMenu() }}>Delete asset</button>}
            </>
          )}
        </div>
      )}
    </div>
  )

  return (
    <section className="pane assets">
      <header>
        <div className="t"><Icon name="aperture" /><span>Assets</span></div>
        <span className="mono" style={{ fontSize: 10, color: 'var(--ink4)' }}>{assets.length}</span>
      </header>
      <div className="body" onClick={closeMenu}>
        <div className="assetlist">
          {folders.map((f) => (
            <div className="folder" key={f}>
              <div className="folder-head" onClick={() => setCollapsed((c) => ({ ...c, [f]: !c[f] }))}>
                <span className="fchev">{collapsed[f] ? '▸' : '▾'}</span>
                <span className="fname">{f}</span>
                <span className="fcount mono">{groupOf(f).length}</span>
              </div>
              {!collapsed[f] && groupOf(f).map(renderAsset)}
            </div>
          ))}
          {ungrouped.map(renderAsset)}
          <label className="dropzone">
            <Icon name="import" />
            <div className="dz">Drop a mesh to bake</div>
            <div className="dz2">.obj · .glb · .stl</div>
            <input type="file" accept=".obj,.glb,.stl" style={{ display: 'none' }}
              onChange={(e) => { const f = e.target.files?.[0]; if (f) onImport(f) }} />
          </label>
        </div>
      </div>
    </section>
  )
}
