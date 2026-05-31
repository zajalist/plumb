import { useRef, useState, type DragEvent } from 'react'
import { Icon } from './Icons'
import type { Asset } from './AssetsPanel'

// Bake-staging settings tweaked before/while baking dropped meshes.
export type BakeSettings = { profile: string; simplify: boolean }

const PROFILES = ['rigid_prop', 'door', 'tree', 'shelf']
const ACCEPT = '.obj,.glb,.gltf,.stl,.uasset,.bin,.png,.jpg,.jpeg,.webp,.ktx2'

function statusLabel(s: Asset['status']): string {
  return s === 'queued' ? 'queued'
    : s === 'converting' ? 'converting · Unreal'
    : s === 'baking' ? 'decomposing · physics'
    : s === 'ok' ? 'ready'
    : s === 'error' ? 'failed'
    : s
}

/* eslint-disable @typescript-eslint/no-explicit-any */
// Recurse a dropped folder (incl. nested subdirs like textures/) into a flat File
// list, so dropping a .gltf's folder auto-collects its .bin + textures. Directory
// entry handles must be grabbed synchronously from the drop event, then read async.
function readEntry(entry: any, out: File[]): Promise<void> {
  if (!entry) return Promise.resolve()
  if (entry.isFile) {
    return new Promise((res) => entry.file((f: File) => { out.push(f); res() }, () => res()))
  }
  const reader = entry.createReader()
  const readBatch = (): Promise<any[]> => new Promise((res) => reader.readEntries((e: any[]) => res(e), () => res([])))
  return (async () => {
    let batch = await readBatch()
    while (batch.length) { for (const e of batch) await readEntry(e, out); batch = await readBatch() }
  })()
}
/* eslint-enable @typescript-eslint/no-explicit-any */

// The screen between import and the editor: drop 3D items, tweak bake settings,
// watch each one bake with a progress bar, then enter the editor.
export function Stage({ assets, settings, setSettings, onAddFiles, onEnter, ueAvailable }: {
  assets: Asset[]
  settings: BakeSettings
  setSettings: (s: BakeSettings) => void
  onAddFiles: (files: File[]) => void
  onEnter: () => void
  ueAvailable: boolean
}) {
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const folderRef = useRef<HTMLInputElement>(null)

  const onDrop = (e: DragEvent) => {
    e.preventDefault(); setDragging(false)
    const dt = e.dataTransfer
    const fallback = Array.from(dt.files)
    // grab directory handles synchronously (invalid once the handler returns), then
    // recurse them so a dropped .gltf folder pulls its nested .bin + textures.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const entries = Array.from(dt.items || []).map((it) => (it as any).webkitGetAsEntry?.()).filter(Boolean)
    if (!entries.length) { if (fallback.length) onAddFiles(fallback); return }
    void (async () => {
      const out: File[] = []
      for (const en of entries) await readEntry(en, out)
      onAddFiles(out.length ? out : fallback)
    })()
  }

  const ready = assets.filter((a) => a.status === 'ok').length
  const active = assets.some((a) => a.status === 'queued' || a.status === 'converting' || a.status === 'baking')

  return (
    <div className="stage-screen">
      <div className="stage-head">
        <span className="wordmark">Plumb</span>
        <span className="stage-sub label">Bake staging</span>
      </div>

      <div className="stage-body">
        <div className="stage-left">
          <div className={`stage-drop${dragging ? ' on' : ''}`}
            onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
            onDragLeave={() => setDragging(false)} onDrop={onDrop}
            onClick={() => inputRef.current?.click()}>
            <Icon name="import" />
            <div className="sd-1">Drop 3D files or a folder</div>
            <div className="sd-2 mono">.obj · .glb · .stl{ueAvailable ? ' · .uasset' : ''}</div>
            <div className="sd-3">a .gltf auto-pulls its .bin + textures (incl. nested folders)</div>
            <button className="sd-folder" onClick={(e) => { e.stopPropagation(); folderRef.current?.click() }}>choose a folder…</button>
            <input ref={inputRef} type="file" accept={ACCEPT} multiple style={{ display: 'none' }}
              onChange={(e) => { const fs = Array.from(e.target.files ?? []); if (fs.length) onAddFiles(fs); e.currentTarget.value = '' }} />
            <input ref={folderRef} type="file" multiple style={{ display: 'none' }}
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              {...({ webkitdirectory: '', directory: '' } as any)}
              onChange={(e) => { const fs = Array.from(e.target.files ?? []); if (fs.length) onAddFiles(fs); e.currentTarget.value = '' }} />
          </div>

          <div className="stage-settings">
            <div className="label">Bake settings</div>
            <div className="ss-row">
              <span className="ss-k">Profile</span>
              <select className="ss-sel" value={settings.profile}
                onChange={(e) => setSettings({ ...settings, profile: e.target.value })}>
                {PROFILES.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>
            <label className="ss-row ss-toggle">
              <span className="ss-k">Simplify dense meshes</span>
              <input type="checkbox" checked={settings.simplify}
                onChange={(e) => setSettings({ ...settings, simplify: e.target.checked })} />
            </label>
            <div className="ss-note">{ueAvailable
              ? 'Unreal .uasset conversion is wired up.'
              : '.uasset needs Unreal (set PLUMB_UE_CMD + PLUMB_UE_PROJECT).'}</div>
          </div>
        </div>

        <div className="stage-queue">
          <div className="sq-head">
            <span className="label">Queue</span>
            <span className="mono sq-count">{ready}/{assets.length} ready</span>
          </div>
          {assets.length === 0 ? (
            <div className="sq-empty">No files yet. Drop meshes to begin.</div>
          ) : (
            <div className="sq-list">
              {assets.map((a) => (
                <div className={`sq-item ${a.status}`} key={a.id}>
                  <div className="sq-top">
                    <span className="sq-name">{a.name}</span>
                    <span className="sq-status mono">{statusLabel(a.status)}</span>
                  </div>
                  <div className="sq-bar"><span className={`sq-fill ${a.status}`} /></div>
                  <div className="sq-meta mono">
                    {a.status === 'ok' && a.pap
                      ? `${a.pap.parts?.length ?? a.pap.geometry.convex_parts} masks · ${a.pap.physical.mass_kg.toFixed(1)} kg`
                      : a.status === 'error'
                        ? <span style={{ color: 'var(--fail)' }}>{a.error}</span>
                        : a.name.toLowerCase().endsWith('.uasset') ? 'unreal asset' : ''}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="stage-foot">
        <button className="stage-enter" onClick={onEnter} disabled={active}>
          {active ? 'Baking…' : ready > 0 ? `Enter editor · ${ready} asset${ready > 1 ? 's' : ''} →` : 'Enter editor →'}
        </button>
      </div>
    </div>
  )
}
