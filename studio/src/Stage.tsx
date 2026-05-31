import { useRef, useState, type DragEvent } from 'react'
import { Icon } from './Icons'
import { Brand } from './Brand'
import type { Asset } from './AssetsPanel'

// Bake-staging settings tweaked before/while baking dropped meshes.
export type BakeSettings = { profile: string; simplify: boolean }

const PROFILES = ['rigid_prop', 'door', 'tree', 'shelf']
const ACCEPT = '.obj,.glb,.gltf,.stl,.uasset'

function statusLabel(s: Asset['status']): string {
  return s === 'queued' ? 'queued'
    : s === 'converting' ? 'converting · Unreal'
    : s === 'baking' ? 'decomposing · physics'
    : s === 'ok' ? 'ready'
    : s === 'error' ? 'failed'
    : s
}

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

  const onDrop = (e: DragEvent) => {
    e.preventDefault(); setDragging(false)
    const files = Array.from(e.dataTransfer.files)
    if (files.length) onAddFiles(files)
  }

  const ready = assets.filter((a) => a.status === 'ok').length
  const active = assets.some((a) => a.status === 'queued' || a.status === 'converting' || a.status === 'baking')

  return (
    <div className="stage-screen">
      <div className="stage-head">
        <Brand />
        <span className="stage-sub label">Bake staging</span>
      </div>

      <div className="stage-body">
        <div className="stage-left">
          <div className={`stage-drop${dragging ? ' on' : ''}`}
            onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
            onDragLeave={() => setDragging(false)} onDrop={onDrop}
            onClick={() => inputRef.current?.click()}>
            <Icon name="import" />
            <div className="sd-1">Drop 3D files to bake</div>
            <div className="sd-2 mono">.obj · .glb · .stl{ueAvailable ? ' · .uasset' : ''}</div>
            <input ref={inputRef} type="file" accept={ACCEPT} multiple style={{ display: 'none' }}
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
            <div className="sq-empty">No files yet — drop meshes to begin.</div>
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
          {active ? 'Baking…' : ready > 0 ? `Enter editor — ${ready} asset${ready > 1 ? 's' : ''} →` : 'Enter editor →'}
        </button>
      </div>
    </div>
  )
}
