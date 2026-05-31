import { useState, useCallback, useEffect } from 'react'
import { IconDefs, Icon } from './Icons'
import { Brand } from './Brand'
import { AssetsPanel, type Asset } from './AssetsPanel'
import { Viewport } from './Viewport'
import { Properties } from './Properties'
import { Inspector } from './Inspector'
import { GateStack } from './GateStack'
import { Splash } from './Splash'
import { Stage, type BakeSettings } from './Stage'
import { LawsBand } from './LawsBand'
import { getRecent, addRecent, type RecentEntry } from './recent'
import { ReactFlowProvider } from '@xyflow/react'
import ConstraintGraph from './components/ConstraintGraph' // Fara's editable node editor
import Palette from './components/Palette'
import { INITIAL_SCENE, type SceneState } from './lib/engine'
import { bake, bakeCached, convertUassets, validate, repair, commit, openWdf, health, type Verdict, type WdfDoc } from './api'
import './App.css'

export default function App() {
  // launch flow: Splash → Stage (drop + bake) → Editor
  const [screen, setScreen] = useState<'splash' | 'stage' | 'editor'>('splash')
  const [recent, setRecent] = useState<RecentEntry[]>(() => getRecent())
  const [settings, setSettings] = useState<BakeSettings>({ profile: 'rigid_prop', simplify: false })
  const [ueAvailable, setUeAvailable] = useState(false)
  const startNew = useCallback(() => setScreen('stage'), [])
  const openProject = useCallback((name: string) => { setRecent(addRecent(name)); setScreen('editor') }, [])

  useEffect(() => { health().then((h) => setUeAvailable(!!h.ue?.available)).catch(() => {}) }, [])

  const [assets, setAssets] = useState<Asset[]>([])
  const [sel, setSel] = useState<string | null>(null)
  const selected = assets.find((a) => a.id === sel) ?? null

  // opened .wdf scene (declared masks + laws), if any
  const [wdf, setWdf] = useState<WdfDoc | null>(null)
  const onOpenFile = useCallback(async (file: File) => {
    if (file.name.toLowerCase().endsWith('.wdf')) {
      try {
        const doc = await openWdf(file)
        setWdf(doc)
        const declared = doc.vocabulary.assets.map((a, i): Asset => ({
          id: `${a.name}-${i}`, name: a.name, status: 'declared', wdf: a,
        }))
        setAssets(declared)
        setSel(declared[0]?.id ?? null)
      } catch (e) {
        console.error('open .wdf failed', e)
      }
    }
    openProject(file.name)
  }, [openProject])

  // placement + live verdict (M2)
  const [pos, setPos] = useState<number[]>([0, 0, 0.4])
  const [verdict, setVerdict] = useState<Verdict | null>(null)
  const [busy, setBusy] = useState(false)
  const [nodeH, setNodeH] = useState(300)

  // node-editor scene (Fara's editable constraint graph; its own live "knob")
  const [scene, setScene] = useState<SceneState>(INITIAL_SCENE)
  const setBronzeX = useCallback((x: number) => setScene((s) => ({ ...s, bronzeX: x })), [])

  const startResize = useCallback((e: React.PointerEvent) => {
    e.preventDefault()
    const handle = e.currentTarget as HTMLElement
    handle.setPointerCapture(e.pointerId)
    const onMove = (ev: PointerEvent) => {
      const h = window.innerHeight - ev.clientY
      setNodeH(Math.min(window.innerHeight - 180, Math.max(180, h)))
    }
    const onUp = (ev: PointerEvent) => {
      handle.releasePointerCapture(ev.pointerId)
      handle.removeEventListener('pointermove', onMove)
      handle.removeEventListener('pointerup', onUp)
      document.body.style.userSelect = ''
    }
    document.body.style.userSelect = 'none'
    handle.addEventListener('pointermove', onMove)
    handle.addEventListener('pointerup', onUp)
  }, [])

  // reset the loop when the selected asset changes
  useEffect(() => { setPos([0, 0, 0.4]); setVerdict(null) }, [sel])

  // Bake one queued file through the real backend, walking its status (converting
  // for .uasset → baking → ok/error) so the stage queue shows live progress.
  const bakeFile = useCallback(async (file: File, id: string, extras?: File[]) => {
    const isU = file.name.toLowerCase().endsWith('.uasset')
    setAssets((a) => a.map((x) => (x.id === id ? { ...x, status: isU ? 'converting' : 'baking' } : x)))
    try {
      const pap = await bake(file, { profile: settings.profile, decimate: settings.simplify ? 6000 : undefined, extras })
      setAssets((a) => a.map((x) => (x.id === id ? { ...x, pap, status: 'ok' } : x)))
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e)
      setAssets((a) => a.map((x) => (x.id === id ? { ...x, status: 'error', error: msg } : x)))
    }
  }, [settings])

  // Add dropped/selected files to the queue, then bake. .uasset files are converted
  // in ONE Unreal boot (batch) and baked from their tokens; meshes bake directly.
  const onAddFiles = useCallback(async (files: File[]) => {
    // mesh files become assets; everything else (.bin, textures) rides along as
    // sidecars for any .gltf in the same drop (a .gltf isn't self-contained).
    const meshFiles = files.filter((f) => /\.(obj|glb|gltf|stl|uasset)$/i.test(f.name))
    const sidecars = files.filter((f) => !/\.(obj|glb|gltf|stl|uasset)$/i.test(f.name))
    if (meshFiles.length === 0) return
    const added = meshFiles.map((f): Asset => ({
      id: `${f.name.replace(/\.[^.]+$/, '')}-${Math.random().toString(36).slice(2, 6)}`,
      name: f.name, file: f, status: 'queued',
    }))
    setAssets((a) => [...a, ...added])
    setSel((s) => s ?? added[0]?.id ?? null)

    const opts = { profile: settings.profile, decimate: settings.simplify ? 6000 : undefined }
    const uassets = added.filter((x) => x.name.toLowerCase().endsWith('.uasset'))
    const meshes = added.filter((x) => !x.name.toLowerCase().endsWith('.uasset'))
    const mark = (id: string, patch: Partial<Asset>) =>
      setAssets((a) => a.map((x) => (x.id === id ? { ...x, ...patch } : x)))

    if (uassets.length) {
      uassets.forEach((u) => mark(u.id, { status: 'converting' }))
      try {
        const results = await convertUassets(uassets.map((u) => u.file!))
        const byName = new Map(results.map((r) => [r.name, r]))
        for (const u of uassets) {
          const res = byName.get(u.name)
          if (!res?.ok || !res.token) { mark(u.id, { status: 'error', error: 'Unreal export failed' }); continue }
          mark(u.id, { status: 'baking' })
          try { mark(u.id, { pap: await bakeCached(res.token, opts), status: 'ok' }) }
          catch (e) { mark(u.id, { status: 'error', error: e instanceof Error ? e.message : String(e) }) }
        }
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e)
        uassets.forEach((u) => mark(u.id, { status: 'error', error: msg }))
      }
    }

    for (const x of meshes) {
      const extras = x.name.toLowerCase().endsWith('.gltf') ? sidecars : undefined
      await bakeFile(x.file!, x.id, extras)
    }
  }, [bakeFile, settings])

  const onImport = useCallback((file: File) => { void onAddFiles([file]) }, [onAddFiles])

  const objId = selected?.pap?.asset_id ?? null

  const onValidate = useCallback(async () => {
    if (!objId) return
    setBusy(true)
    try { setVerdict(await validate(objId, pos)) } finally { setBusy(false) }
  }, [objId, pos])

  const onRepair = useCallback(async () => {
    if (!objId) return
    setBusy(true)
    try {
      const tf = await repair(objId, pos)
      const rounded = tf.pos.map((v) => Math.round(v * 1000) / 1000) // mm precision, no e-notation
      setPos(rounded)
      setVerdict(await validate(objId, rounded, tf.quat))
    } finally { setBusy(false) }
  }, [objId, pos])

  const onCommit = useCallback(async () => {
    if (!objId) return
    setBusy(true)
    try { await commit(objId, pos) } finally { setBusy(false) }
  }, [objId, pos])

  // material-confirm loop: re-bake the selected mesh with the confirmed per-part
  // materials (now they drive physics) and lock them into the PAP.
  const onConfirmMaterials = useCallback(async (materials: Record<string, string>) => {
    if (!selected?.file) return
    setBusy(true)
    try {
      const pap = await bake(selected.file, { materials, profile: settings.profile })
      setAssets((a) => a.map((x) => (x.id === selected.id ? { ...x, pap, status: 'ok' } : x)))
    } finally { setBusy(false) }
  }, [selected, settings])

  const inspector = selected?.status === 'ok' && objId
    ? <Inspector pos={pos} setPos={setPos} verdict={verdict} busy={busy}
        onValidate={onValidate} onRepair={onRepair} onCommit={onCommit} />
    : undefined

  if (screen === 'splash') {
    return (
      <>
        <IconDefs />
        <Splash recent={recent} onNew={startNew}
          onOpen={onOpenFile} onOpenRecent={(e) => openProject(e.name)} />
      </>
    )
  }

  if (screen === 'stage') {
    return (
      <>
        <IconDefs />
        <Stage assets={assets} settings={settings} setSettings={setSettings}
          onAddFiles={onAddFiles} onEnter={() => setScreen('editor')} ueAvailable={ueAvailable} />
      </>
    )
  }

  return (
    <div className="app">
      <IconDefs />

      <div className="menubar">
        <Brand />
        <div className="sep" />
        <div className="mfile">
          <div className="mbtn"><Icon name="new" />New</div>
          <div className="mbtn"><Icon name="open" />Open</div>
          <label className="mbtn key">
            <Icon name="import" />Import mesh
            <input type="file" multiple accept=".obj,.glb,.gltf,.stl,.uasset,.bin,.png,.jpg,.jpeg,.webp,.ktx2"
              style={{ display: 'none' }}
              onChange={(e) => { const fs = Array.from(e.target.files ?? []); if (fs.length) onAddFiles(fs); e.currentTarget.value = '' }} />
          </label>
        </div>
        <div className="proj">
          <span className="dot" /><span className="mono">{wdf?.scene ? `${wdf.scene.name}.wdf` : 'untitled.wdf'}</span>
          <span style={{ color: 'var(--ink4)' }}>·</span>{assets.length} assets
        </div>
      </div>

      <GateStack verdict={verdict} />
      {wdf?.scene && <LawsBand scene={wdf.scene} />}

      <div className="row">
        <AssetsPanel assets={assets} selected={sel} onSelect={setSel} onImport={onImport} />
        <Viewport name={selected?.name ?? ''}
          pap={selected?.pap ?? null} pos={pos} verdict={verdict} status={selected?.status} />
        <Properties pap={selected?.pap ?? null} footer={inspector}
          onConfirm={onConfirmMaterials} busy={busy} declared={selected?.wdf} />
      </div>

      <div
        className="resize-handle"
        onPointerDown={startResize}
        role="separator"
        aria-orientation="horizontal"
        title="Drag to resize the node editor"
      />

      <div className="nodeeditor" style={{ height: nodeH }}>
        <header>
          <Icon name="reach" /><span className="t">Node editor</span><span className="who">Fara</span>
        </header>
        <div className="ne">
          <ReactFlowProvider>
            <Palette />
            <ConstraintGraph scene={scene} setBronzeX={setBronzeX} />
          </ReactFlowProvider>
        </div>
      </div>
    </div>
  )
}
