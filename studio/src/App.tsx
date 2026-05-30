import { useState, useCallback, useEffect } from 'react'
import { IconDefs, Icon } from './Icons'
import { Brand } from './Brand'
import { AssetsPanel, type Asset } from './AssetsPanel'
import { Viewport } from './Viewport'
import { Properties } from './Properties'
import { Inspector } from './Inspector'
import { GateStack } from './GateStack'
import ConstraintGraph from './ConstraintGraph' // Fara's — unchanged
import { bake, validate, repair, commit, type Verdict } from './api'
import { attempts } from './verdicts'
import './App.css'

export default function App() {
  const [assets, setAssets] = useState<Asset[]>([])
  const [sel, setSel] = useState<string | null>(null)
  const selected = assets.find((a) => a.id === sel) ?? null

  // placement + live verdict (M2)
  const [pos, setPos] = useState<number[]>([0, 0, 0.4])
  const [verdict, setVerdict] = useState<Verdict | null>(null)
  const [busy, setBusy] = useState(false)

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

  const inspector = selected?.status === 'ok' && objId
    ? <Inspector pos={pos} setPos={setPos} verdict={verdict} busy={busy}
        onValidate={onValidate} onRepair={onRepair} onCommit={onCommit} />
    : undefined

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
          <span className="dot" /><span className="mono">untitled.wdf</span>
          <span style={{ color: 'var(--ink4)' }}>·</span>{assets.length} assets
        </div>
      </div>

      <GateStack verdict={verdict} />

      <div className="row">
        <AssetsPanel assets={assets} selected={sel} onSelect={setSel} onImport={onImport} />
        <Viewport file={selected?.file ?? null} name={selected?.name ?? ''}
          pap={selected?.pap ?? null} pos={pos} verdict={verdict} />
        <Properties pap={selected?.pap ?? null} footer={inspector} />
      </div>

      <div className="nodeeditor">
        <header>
          <Icon name="reach" /><span className="t">Node editor</span><span className="who">Fara</span>
        </header>
        <div className="ne">
          <ConstraintGraph attempt={attempts[0]} />
        </div>
      </div>
    </div>
  )
}
