import { useEffect, useRef, useState } from 'react'
import { listProjects, type ProjectInfo } from './api'

// The top menu bar: a text wordmark + working dropdown menus. Every item does a
// real thing — file dialogs, undo/redo (dispatched to the node editor's global key
// handler), fullscreen, docs, about.
type Item = 'sep' | { label: string; accel?: string; onClick?: () => void; disabled?: boolean; checked?: boolean }

type Panels = { assets: boolean; properties: boolean; gates: boolean; nodeEditor: boolean }

export function Menubar({ projectName, assetCount, onNew, onOpenWdf, onImport, onSaveProject, onOpenProject, panels, onTogglePanel }: {
  projectName: string
  assetCount: number
  onNew: () => void
  onOpenWdf: (file: File) => void
  onImport: (files: File[]) => void
  onSaveProject?: (name: string) => void | Promise<void>
  onOpenProject?: (name: string) => void | Promise<void>
  panels?: Panels
  onTogglePanel?: (k: keyof Panels) => void
}) {
  const [open, setOpen] = useState<string | null>(null)
  const [about, setAbout] = useState(false)
  const [saveOpen, setSaveOpen] = useState(false)
  const [saveName, setSaveName] = useState('')
  const [saving, setSaving] = useState(false)
  const [openOpen, setOpenOpen] = useState(false)
  const [projects, setProjects] = useState<ProjectInfo[] | null>(null)
  const [isFull, setIsFull] = useState(() => !!document.fullscreenElement)
  useEffect(() => {
    const h = () => setIsFull(!!document.fullscreenElement)
    document.addEventListener('fullscreenchange', h)
    return () => document.removeEventListener('fullscreenchange', h)
  }, [])
  const barRef = useRef<HTMLDivElement>(null)
  const wdfInput = useRef<HTMLInputElement>(null)
  const meshInput = useRef<HTMLInputElement>(null)

  const doSave = async () => {
    const name = saveName.trim()
    if (!name || !onSaveProject) return
    setSaving(true)
    try { await onSaveProject(name); setSaveOpen(false); setSaveName('') }
    finally { setSaving(false) }
  }
  const openPicker = async () => {
    setOpenOpen(true); setProjects(null)
    try { setProjects(await listProjects()) } catch { setProjects([]) }
  }

  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => { if (barRef.current && !barRef.current.contains(e.target as Node)) setOpen(null) }
    const onEsc = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(null) }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onEsc)
    return () => { document.removeEventListener('mousedown', onDoc); document.removeEventListener('keydown', onEsc) }
  }, [open])

  const sendKey = (k: string, shift = false) =>
    window.dispatchEvent(new KeyboardEvent('keydown', { key: k, ctrlKey: true, shiftKey: shift, bubbles: true }))
  const fullscreen = () => {
    if (document.fullscreenElement) document.exitFullscreen()
    else document.documentElement.requestFullscreen?.()
  }

  const MENUS: Record<string, Item[]> = {
    File: [
      { label: 'New project', accel: 'Ctrl N', onClick: onNew },
      { label: 'Open project…', onClick: openPicker, disabled: !onOpenProject },
      { label: 'Save project…', accel: 'Ctrl S', onClick: () => { setSaveName(projectName && projectName !== 'untitled' ? projectName : ''); setSaveOpen(true) }, disabled: !onSaveProject || assetCount === 0 },
      'sep',
      { label: 'Open .wdf…', accel: 'Ctrl O', onClick: () => wdfInput.current?.click() },
      { label: 'Import mesh…', accel: 'Ctrl I', onClick: () => meshInput.current?.click() },
    ],
    Edit: [
      { label: 'Undo', accel: 'Ctrl Z', onClick: () => sendKey('z') },
      { label: 'Redo', accel: 'Ctrl Y', onClick: () => sendKey('z', true) },
    ],
    View: [
      { label: isFull ? 'Exit fullscreen' : 'Fullscreen', accel: 'F11', onClick: fullscreen },
    ],
    Window: [
      { label: 'Gate stack', checked: panels?.gates ?? true, onClick: () => onTogglePanel?.('gates') },
      { label: 'Assets', checked: panels?.assets ?? true, onClick: () => onTogglePanel?.('assets') },
      { label: 'Properties', checked: panels?.properties ?? true, onClick: () => onTogglePanel?.('properties') },
      { label: 'Node editor', checked: panels?.nodeEditor ?? true, onClick: () => onTogglePanel?.('nodeEditor') },
    ],
    Tools: [
      { label: 'New bake…', onClick: onNew },
    ],
    Help: [
      { label: 'Documentation', onClick: () => window.open('https://github.com/zajalist/plumb', '_blank', 'noopener') },
      'sep',
      { label: 'About Plumb', onClick: () => setAbout(true) },
    ],
  }

  const run = (it: Exclude<Item, 'sep'>) => {
    if (it.disabled) return
    it.onClick?.()
    if (it.checked === undefined) setOpen(null)   // toggles keep the menu open
  }

  return (
    <div className="menubar" ref={barRef}>
      <span className="wordmark">Plumb</span>
      <div className="sep" />
      <nav className="menus">
        {Object.entries(MENUS).map(([name, items]) => (
          <div className="menu" key={name}>
            <button
              className={`menu-btn${open === name ? ' on' : ''}`}
              onClick={() => setOpen(open === name ? null : name)}
              onMouseEnter={() => { if (open) setOpen(name) }}
            >{name}</button>
            {open === name && (
              <div className="menu-pop">
                {items.map((it, i) => it === 'sep'
                  ? <div className="menu-sep" key={i} />
                  : (
                    <button className={`menu-item${it.checked !== undefined ? ' toggle' : ''}${it.checked ? ' on' : ''}`} key={i} disabled={it.disabled} onClick={() => run(it)}>
                      <span>{it.label}</span>
                      {it.checked !== undefined
                        ? <span className="mi-sw" aria-hidden />
                        : it.accel && <span className="accel">{it.accel}</span>}
                    </button>
                  ))}
              </div>
            )}
          </div>
        ))}
      </nav>
      <div className="proj">
        <span className="mono">{projectName}</span>
        <span style={{ color: 'var(--ink4)' }}>·</span>{assetCount} assets
      </div>

      <input ref={wdfInput} type="file" accept=".wdf" style={{ display: 'none' }}
        onChange={(e) => { const f = e.target.files?.[0]; if (f) onOpenWdf(f); e.currentTarget.value = '' }} />
      <input ref={meshInput} type="file" multiple
        accept=".obj,.glb,.gltf,.stl,.uasset,.bin,.png,.jpg,.jpeg,.webp,.ktx2" style={{ display: 'none' }}
        onChange={(e) => { const fs = Array.from(e.target.files ?? []); if (fs.length) onImport(fs); e.currentTarget.value = '' }} />

      {about && (
        <div className="modal-scrim" onClick={() => setAbout(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="wordmark" style={{ fontSize: 34 }}>Plumb</div>
            <p style={{ marginTop: 8, color: 'var(--ink2)' }}>Spatial validation for physically-grounded 3D worlds.</p>
            <p className="mono" style={{ marginTop: 10, color: 'var(--ink4)', fontSize: 11 }}>v0.1 · local cortex</p>
            <button className="menu-item modal-close" onClick={() => setAbout(false)}>Close</button>
          </div>
        </div>
      )}

      {saveOpen && (
        <div className="modal-scrim" onClick={() => !saving && setSaveOpen(false)}>
          <div className="modal proj-modal" onClick={(e) => e.stopPropagation()}>
            <div className="pm-h">Save project</div>
            <p className="pm-sub">Saves the <span className="mono">.wdf</span> semantics and the {assetCount} model{assetCount === 1 ? '' : 's'} together.</p>
            <input className="pm-input" autoFocus placeholder="Project name…" value={saveName}
              onChange={(e) => setSaveName(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') void doSave(); else if (e.key === 'Escape') setSaveOpen(false) }} />
            <div className="pm-actions">
              <button className="menu-item" onClick={() => setSaveOpen(false)} disabled={saving}>Cancel</button>
              <button className="pm-go" onClick={() => void doSave()} disabled={saving || !saveName.trim()}>{saving ? 'Saving…' : 'Save'}</button>
            </div>
          </div>
        </div>
      )}

      {openOpen && (
        <div className="modal-scrim" onClick={() => setOpenOpen(false)}>
          <div className="modal proj-modal" onClick={(e) => e.stopPropagation()}>
            <div className="pm-h">Open project</div>
            <div className="pm-list">
              {projects === null && <div className="pm-empty">Loading…</div>}
              {projects?.length === 0 && <div className="pm-empty">No saved projects yet.</div>}
              {projects?.map((p) => (
                <button className="pm-row" key={p.name}
                  onClick={async () => { setOpenOpen(false); await onOpenProject?.(p.name) }}>
                  <span className="pm-name">{p.name}</span>
                  <span className="pm-meta mono">{p.assets} asset{p.assets === 1 ? '' : 's'}</span>
                </button>
              ))}
            </div>
            <div className="pm-actions">
              <button className="menu-item" onClick={() => setOpenOpen(false)}>Close</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
