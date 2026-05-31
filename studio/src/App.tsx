import { useState, useCallback, useEffect } from 'react'
import { IconDefs, Icon } from './Icons'
import { Brand } from './Brand'
import { AssetsPanel, type Asset } from './AssetsPanel'
import { Viewport } from './Viewport'
import { Properties } from './Properties'
import { Inspector } from './Inspector'
import { GateStack } from './GateStack'
import { Splash } from './Splash'
import { LawsBand } from './LawsBand'
import { getRecent, addRecent, type RecentEntry } from './recent'
import { ReactFlowProvider } from '@xyflow/react'
import ConstraintGraph from './components/ConstraintGraph' // Fara's editable node editor
import Palette from './components/Palette'
import { INITIAL_SCENE, type SceneState } from './lib/engine'
import { bake, validate, repair, commit, openWdf, type Verdict, type WdfDoc } from './api'
import './App.css'

export default function App() {
  // launch flow: Splash → IDE (WP-1)
  const [started, setStarted] = useState(false)
  const [recent, setRecent] = useState<RecentEntry[]>(() => getRecent())
  const startNew = useCallback(() => setStarted(true), [])
  const openProject = useCallback((name: string) => { setRecent(addRecent(name)); setStarted(true) }, [])

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

  // node-editor scene (Fara's editable constraint graph; its own live "knob")
  const [scene, setScene] = useState<SceneState>(INITIAL_SCENE)
  const setBronzeX = useCallback((x: number) => setScene((s) => ({ ...s, bronzeX: x })), [])

  // reset the loop when the selected asset changes
  useEffect(() => { setPos([0, 0, 0.4]); setVerdict(null) }, [sel])

  const onImport = useCallback(async (file: File) => {
    const base = file.name.replace(/\.[^.]+$/, '')
    const id = `${base}-${Math.random().toString(36).slice(2, 6)}`
    setAssets((a) => [...a, { id, name: file.name, file, status: 'baking' }])
    setSel(id)
    try {
      const pap = await bake(file)
      setAssets((a) => a.map((x) => (x.id === id ? { ...x, pap, status: 'ok' } : x)))
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e)
      setAssets((a) => a.map((x) => (x.id === id ? { ...x, status: 'error', error: msg } : x)))
    }
  }, [])

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
      const pap = await bake(selected.file, materials)
      setAssets((a) => a.map((x) => (x.id === selected.id ? { ...x, pap, status: 'ok' } : x)))
    } finally { setBusy(false) }
  }, [selected])

  const inspector = selected?.status === 'ok' && objId
    ? <Inspector pos={pos} setPos={setPos} verdict={verdict} busy={busy}
        onValidate={onValidate} onRepair={onRepair} onCommit={onCommit} />
    : undefined

  if (!started) {
    return (
      <>
        <IconDefs />
        <Splash recent={recent} onNew={startNew}
          onOpen={onOpenFile} onOpenRecent={(e) => openProject(e.name)} />
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
            <input type="file" accept=".obj,.glb,.stl" style={{ display: 'none' }}
              onChange={(e) => { const f = e.target.files?.[0]; if (f) onImport(f) }} />
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
        <Viewport file={selected?.file ?? null} name={selected?.name ?? ''}
          pap={selected?.pap ?? null} pos={pos} verdict={verdict} />
        <Properties pap={selected?.pap ?? null} footer={inspector}
          onConfirm={onConfirmMaterials} busy={busy} declared={selected?.wdf} />
      </div>

      <div className="nodeeditor">
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
