import { useState, useCallback } from 'react'
import { IconDefs, Icon } from './Icons'
import { Brand } from './Brand'
import { AssetsPanel, type Asset } from './AssetsPanel'
import { Viewport } from './Viewport'
import { Properties } from './Properties'
import { GateStack } from './GateStack'
import ConstraintGraph from './ConstraintGraph' // Fara's — unchanged
import { bake } from './api'
import { attempts } from './verdicts'
import './App.css'

export default function App() {
  const [assets, setAssets] = useState<Asset[]>([])
  const [sel, setSel] = useState<string | null>(null)
  const selected = assets.find((a) => a.id === sel) ?? null

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

  // Fixture verdict drives the gate stack + Fara's graph until M2 wires live /validate.
  const attempt = attempts[0]

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

      <GateStack attempt={attempt} />

      <div className="row">
        <AssetsPanel assets={assets} selected={sel} onSelect={setSel} onImport={onImport} />
        <Viewport file={selected?.file ?? null} name={selected?.name ?? ''} />
        <Properties pap={selected?.pap ?? null} />
      </div>

      <div className="nodeeditor">
        <header>
          <Icon name="reach" /><span className="t">Node editor</span><span className="who">Fara</span>
        </header>
        <div className="ne">
          <ConstraintGraph attempt={attempt} />
        </div>
      </div>
    </div>
  )
}
