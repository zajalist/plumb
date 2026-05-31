import { useEffect, useRef, useState } from 'react'

// The top menu bar: a text wordmark + working dropdown menus. Every item does a
// real thing — file dialogs, undo/redo (dispatched to the node editor's global key
// handler), fullscreen, docs, about.
type Item = 'sep' | { label: string; accel?: string; onClick?: () => void; disabled?: boolean }

export function Menubar({ projectName, assetCount, onNew, onOpenWdf, onImport }: {
  projectName: string
  assetCount: number
  onNew: () => void
  onOpenWdf: (file: File) => void
  onImport: (files: File[]) => void
}) {
  const [open, setOpen] = useState<string | null>(null)
  const [about, setAbout] = useState(false)
  const barRef = useRef<HTMLDivElement>(null)
  const wdfInput = useRef<HTMLInputElement>(null)
  const meshInput = useRef<HTMLInputElement>(null)

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
      { label: 'Open .wdf…', accel: 'Ctrl O', onClick: () => wdfInput.current?.click() },
      { label: 'Import mesh…', accel: 'Ctrl I', onClick: () => meshInput.current?.click() },
    ],
    Edit: [
      { label: 'Undo', accel: 'Ctrl Z', onClick: () => sendKey('z') },
      { label: 'Redo', accel: 'Ctrl Y', onClick: () => sendKey('z', true) },
    ],
    View: [
      { label: document.fullscreenElement ? 'Exit fullscreen' : 'Fullscreen', accel: 'F11', onClick: fullscreen },
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

  const run = (it: Exclude<Item, 'sep'>) => { if (it.disabled) return; setOpen(null); it.onClick?.() }

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
                    <button className="menu-item" key={i} disabled={it.disabled} onClick={() => run(it)}>
                      <span>{it.label}</span>{it.accel && <span className="accel">{it.accel}</span>}
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
    </div>
  )
}
