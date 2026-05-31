import { useRef, useState, type DragEvent } from 'react'
import { Icon } from './Icons'
import { SearchSelect } from './SearchSelect'
import { PROFILE_OPTIONS, PROFILE_BASE } from './lib/bakeCatalog'
import type { Asset } from './AssetsPanel'

// Bake-staging settings tweaked before/while baking dropped meshes.
export type BakeSettings = {
  profile: string          // default profile applied to newly dropped meshes
  simplify: boolean        // decimate dense meshes before decomposition
  decimate?: number        // target face count when simplify is on
  autoCap?: boolean        // auto-close open meshes so mass/volume are real
}

// hint keyed by engine archetype (presets map to one of these via PROFILE_BASE)
const PROFILE_HINT: Record<string, string> = {
  rigid_prop: 'Static prop. One rigid body.',
  door: 'Hinged. Swept hull over the joint range.',
  tree: 'Foliage. Trunk and canopy split.',
  shelf: 'Container. Load surfaces and capacity.',
}
const profileHint = (v: string) => PROFILE_HINT[PROFILE_BASE[v] ?? v] ?? 'Custom preset.'
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
export function Stage({ assets, settings, setSettings, onAddFiles, onBake, onUpdateAsset, onRemove, onEnter, ueAvailable }: {
  assets: Asset[]
  settings: BakeSettings
  setSettings: (s: BakeSettings) => void
  onAddFiles: (files: File[]) => void
  onBake: () => void
  onUpdateAsset: (id: string, patch: Partial<Asset>) => void
  onRemove: (id: string) => void
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
  // queued OR previously-errored meshes can (re)bake — both need a file
  const toBake = assets.filter((a) => (a.status === 'queued' || a.status === 'error') && a.file).length
  const failed = assets.filter((a) => a.status === 'error').length
  const baking = assets.some((a) => a.status === 'converting' || a.status === 'baking')
  const ext = (n: string) => { const m = /\.([a-z0-9]+)$/i.exec(n); return m ? m[1].toUpperCase() : '3D' }

  return (
    <div className="stage-screen">
      <div className="stage-head">
        <span className="wordmark">Plumb</span>
        <span className="sh-sep" />
        <span className="stage-sub label">Bake Staging</span>
        <span className="sh-spring" />
        <span className="sh-stat mono">{ready}/{assets.length} ready</span>
      </div>

      <div className="stage-body">
        <div className="stage-left">
          <section className="upanel">
            <header className="upanel-hd"><Icon name="import" /><span>Import</span></header>
            <div className="upanel-bd">
              <div className={`stage-drop${dragging ? ' on' : ''}`}
                onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
                onDragLeave={() => setDragging(false)} onDrop={onDrop}
                onClick={() => inputRef.current?.click()}>
                <Icon name="import" />
                <div className="sd-1">Drop 3D files or a folder</div>
                <div className="sd-2 mono">.obj · .glb · .stl{ueAvailable ? ' · .uasset' : ''}</div>
                <div className="sd-3">a .gltf auto-pulls its .bin + textures (incl. nested folders)</div>
                <button className="sd-folder" onClick={(e) => { e.stopPropagation(); folderRef.current?.click() }}>Choose a folder…</button>
                <input ref={inputRef} type="file" accept={ACCEPT} multiple style={{ display: 'none' }}
                  onChange={(e) => { const fs = Array.from(e.target.files ?? []); if (fs.length) onAddFiles(fs); e.currentTarget.value = '' }} />
                <input ref={folderRef} type="file" multiple style={{ display: 'none' }}
                  // eslint-disable-next-line @typescript-eslint/no-explicit-any
                  {...({ webkitdirectory: '', directory: '' } as any)}
                  onChange={(e) => { const fs = Array.from(e.target.files ?? []); if (fs.length) onAddFiles(fs); e.currentTarget.value = '' }} />
              </div>
            </div>
          </section>

          <section className="upanel">
            <header className="upanel-hd"><Icon name="aperture" /><span>Bake Settings</span></header>
            <div className="upanel-bd stage-settings">
              <div className="ss-row ss-stack">
                <span className="ss-k">Default profile</span>
                <SearchSelect value={settings.profile} options={PROFILE_OPTIONS}
                  placeholder="Search profiles…"
                  onChange={(v) => setSettings({ ...settings, profile: v })} />
              </div>
              <div className="ss-hint">{profileHint(settings.profile)} Override per mesh in the queue.</div>
              <div className="ss-div" />
              <label className="ss-row ss-toggle">
                <span className="ss-k">Simplify dense meshes</span>
                <input type="checkbox" checked={settings.simplify}
                  onChange={(e) => setSettings({ ...settings, simplify: e.target.checked })} />
              </label>
              {settings.simplify && (
                <div className="ss-row ss-sub">
                  <span className="ss-k">Target faces</span>
                  <input className="ss-num" type="number" min={500} max={200000} step={500}
                    value={settings.decimate ?? 6000}
                    onChange={(e) => setSettings({ ...settings, decimate: Math.max(500, Number(e.target.value) || 6000) })} />
                </div>
              )}
              <label className="ss-row ss-toggle">
                <span className="ss-k">Auto-close open meshes</span>
                <input type="checkbox" checked={!!settings.autoCap}
                  onChange={(e) => setSettings({ ...settings, autoCap: e.target.checked })} />
              </label>
              <div className="ss-hint">Caps open surfaces so mass &amp; volume are computed, not estimated.</div>
              <div className="ss-div" />
              <div className="ss-note">{ueAvailable
                ? 'Unreal .uasset conversion is wired up.'
                : '.uasset needs Unreal (set PLUMB_UE_CMD + PLUMB_UE_PROJECT).'}</div>
            </div>
          </section>
        </div>

        <section className="upanel stage-queue">
          <header className="upanel-hd"><Icon name="grid" /><span>Queue</span><span className="sq-count mono">{ready}/{assets.length} ready</span></header>
          <div className="upanel-bd">
            {assets.length === 0 ? (
              <div className="sq-empty">No files yet. Drop meshes to begin.</div>
            ) : (
              <div className="sq-list">
                {assets.map((a) => (
                  <div className={`sq-item ${a.status}`} key={a.id}>
                    <span className={`sq-tile ${a.status}`}>{ext(a.name)}</span>
                    <div className="sq-main">
                      <div className="sq-top">
                        <span className="sq-name">{a.name}</span>
                        <span className="sq-status mono">{statusLabel(a.status)}</span>
                        <button className="sq-x" title="Remove from queue"
                          onClick={() => onRemove(a.id)}>✕</button>
                      </div>
                      {a.status === 'queued' && a.file ? (
                        <div className="sq-prof">
                          <span className="sq-prof-k">Profile</span>
                          <SearchSelect value={a.profile ?? settings.profile} options={PROFILE_OPTIONS}
                            placeholder="Search profiles…"
                            onChange={(v) => onUpdateAsset(a.id, { profile: v })} />
                        </div>
                      ) : (
                        <div className="sq-bar"><span className={`sq-fill ${a.status}`} /></div>
                      )}
                      <div className="sq-meta mono">
                        {a.status === 'ok' && a.pap
                          ? `${a.profile ?? settings.profile} · ${a.pap.parts?.length ?? a.pap.geometry.convex_parts} masks · ${a.pap.physical.mass_kg.toFixed(1)} kg`
                          : a.status === 'error'
                            ? <span style={{ color: 'var(--fail)' }}>{a.error}</span>
                            : a.name.toLowerCase().endsWith('.uasset') ? 'unreal asset' : ''}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>
      </div>

      <div className="stage-foot">
        {ready > 0 && toBake > 0 && !baking && (
          <button className="stage-enter ghost" onClick={onEnter}>Enter editor · {ready} →</button>
        )}
        <button className="stage-enter" disabled={baking || (toBake === 0 && ready === 0)}
          onClick={toBake > 0 ? onBake : onEnter}>
          {baking ? 'Baking…'
            : toBake > 0 ? `${failed > 0 && toBake === failed ? 'Retry' : 'Bake'} ${toBake} mesh${toBake > 1 ? 'es' : ''}`
            : ready > 0 ? `Enter editor · ${ready} asset${ready > 1 ? 's' : ''} →`
            : 'Drop a mesh to begin'}
        </button>
      </div>
    </div>
  )
}
