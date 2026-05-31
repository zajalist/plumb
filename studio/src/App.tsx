import { useState, useCallback, useEffect, useMemo } from 'react'
import { IconDefs, Icon } from './Icons'
import { Menubar } from './Menubar'
import { AssetsPanel, type Asset } from './AssetsPanel'
import { Viewport } from './Viewport'
import { Properties } from './Properties'
import { PlacementTool } from './PlacementTool'
import { GateStack } from './GateStack'
import { Splash } from './Splash'
import { Stage, type BakeSettings } from './Stage'
import { LawsBand } from './LawsBand'
import { getRecent, addRecent, removeRecent, type RecentEntry } from './recent'
import { ReactFlowProvider } from '@xyflow/react'
import ConstraintGraph from './components/ConstraintGraph' // Fara's editable node editor
import Palette from './components/Palette'
import { INITIAL_SCENE, type SceneState } from './lib/engine'
import { PROFILE_BASE } from './lib/bakeCatalog'
import { bake, bakeCached, convertUassets, validate, repair, commit, openWdf, health,
  saveProject, openProjectData, fetchProjectFile, classifyCap,
  type Verdict, type WdfDoc, type PAP, type Swept, type CapPlane, type CapResult, type ProjectAsset } from './api'
import './App.css'

// Hamilton product q = a ⊗ b (applies b first, then a), all [x,y,z,w].
function qmul(a: number[], b: number[]): number[] {
  const [ax, ay, az, aw] = a, [bx, by, bz, bw] = b
  return [
    aw * bx + ax * bw + ay * bz - az * by,
    aw * by - ax * bz + ay * bw + az * bx,
    aw * bz + ax * by - ay * bx + az * bw,
    aw * bw - ax * bx - ay * by - az * bz,
  ]
}

export default function App() {
  // launch flow: Splash → Stage (drop + bake) → Editor
  const [screen, setScreen] = useState<'splash' | 'stage' | 'editor'>('splash')
  const [recent, setRecent] = useState<RecentEntry[]>(() => getRecent())
  const [settings, setSettings] = useState<BakeSettings>({ profile: 'rigid_prop', simplify: false })
  const [ueAvailable, setUeAvailable] = useState(false)
  const startNew = useCallback(() => setScreen('stage'), [])

  useEffect(() => { health().then((h) => setUeAvailable(!!h.ue?.available)).catch(() => {}) }, [])

  const [assets, setAssets] = useState<Asset[]>([])
  const [sel, setSel] = useState<string | null>(null)
  const selected = assets.find((a) => a.id === sel) ?? null

  const [projectName, setProjectName] = useState<string | null>(null)
  // opened .wdf scene (declared masks + laws), if any
  const [wdf, setWdf] = useState<WdfDoc | null>(null)
  // Open a .wdf world document (declares assets + laws). This is an import, not a
  // saved project — so it goes straight to the editor and is NOT tracked in Recent
  // (Recent is for saved projects, which reopen by name via /project/open).
  const onOpenFile = useCallback(async (file: File) => {
    if (!file.name.toLowerCase().endsWith('.wdf')) {
      alert(`"${file.name}" isn't a .wdf. Use New project to import and bake meshes.`)
      return
    }
    try {
      const doc = await openWdf(file)
      setWdf(doc)
      const declared = doc.vocabulary.assets.map((a, i): Asset => ({
        id: `${a.name}-${i}`, name: a.name, status: 'declared', wdf: a,
      }))
      setAssets(declared)
      setSel(declared[0]?.id ?? null)
      setProjectName(file.name)
      setScreen('editor')
    } catch (e) {
      console.error('open .wdf failed', e)
      alert(`Could not open ${file.name}: ${e instanceof Error ? e.message : 'parse error'}`)
    }
  }, [])

  // placement + live verdict (M2)
  const [pos, setPos] = useState<number[]>([0, 0, 0])
  const [rot, setRot] = useState<number[]>([0, 0, 0])   // placement rotation (euler°), feeds the quat
  const [scale, setScale] = useState(1)                 // uniform placement scale, feeds the transform
  const [verdict, setVerdict] = useState<Verdict | null>(null)
  // Stability support model. Free-standing (default) = the base co-moves with the
  // body, so lateral placement doesn't topple it; off → the anchored pedestal model.
  const [freeStanding, setFreeStanding] = useState(true)
  const [busy, setBusy] = useState(false)
  const [nodeH, setNodeH] = useState(300)
  // resizable docked columns (assets | viewport | properties)
  const [leftW, setLeftW] = useState(248)
  const [rightW, setRightW] = useState(296)
  // toggleable panels (Window menu in the topbar). Viewport is always shown.
  const [panels, setPanels] = useState({ assets: true, properties: true, gates: true, nodeEditor: true })
  const togglePanel = useCallback((k: keyof typeof panels) => setPanels((p) => ({ ...p, [k]: !p[k] })), [])

  // door swing articulation (WP-6): the swept wedge shown in the viewport. The control
  // lives in the node editor (articulation is a graph concern), not the Properties pane.
  const [sweptGeo, setSweptGeo] = useState<Swept | null>(null)

  // node-editor scene (the constraint graph's static fallback context)
  const [scene] = useState<SceneState>(INITIAL_SCENE)

  // Baked assets, as the node editor's selectable Objects (P1 sync). Import &
  // bake → the asset appears in every Object node's dropdown (SYNC.md).
  const objects = useMemo(
    () => {
      const seen = new Set<string>()
      return assets
        .filter((a) => a.status === 'ok' && a.pap)
        .map((a) => ({
          id: a.pap!.asset_id,
          label: a.name,
          sub: `${a.pap!.semantics.cls} · ${a.pap!.physical.mass_kg.toFixed(1)}kg`,
          mass: a.pap!.physical.mass_kg,
          com: a.pap!.physical.com,
          profile: a.pap!.profile, // bake archetype → drives profile auto-graphs (e.g. 'door')
        }))
        .filter((o) => (seen.has(o.id) ? false : (seen.add(o.id), true))) // de-dupe colliding asset_ids
    },
    [assets],
  )

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

  // drag a vertical splitter to rescale the assets ('l') or properties ('r') column
  const startColResize = useCallback((which: 'l' | 'r') => (e: React.PointerEvent) => {
    e.preventDefault()
    const handle = e.currentTarget as HTMLElement
    handle.setPointerCapture(e.pointerId)
    const startX = e.clientX
    const startL = leftW, startR = rightW
    const onMove = (ev: PointerEvent) => {
      const dx = ev.clientX - startX
      if (which === 'l') setLeftW(Math.min(520, Math.max(180, startL + dx)))
      else setRightW(Math.min(560, Math.max(220, startR - dx)))
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
  }, [leftW, rightW])

  // reset the loop when the selected asset changes
  useEffect(() => { setPos([0, 0, 0]); setRot([0, 0, 0]); setScale(1); setVerdict(null); setSweptGeo(null) }, [sel])

  // shared bake options from the global settings (a per-mesh profile overrides .profile).
  // Profiles are rich presets; the bake gets the underlying engine archetype.
  const bakeOpts = useCallback((profile?: string) => {
    const p = profile ?? settings.profile
    return {
      profile: PROFILE_BASE[p] ?? p,
      decimate: settings.simplify ? (settings.decimate ?? 6000) : undefined,
      cap: settings.autoCap,
    }
  }, [settings])

  // Bake one queued file through the real backend, walking its status (converting
  // for .uasset → baking → ok/error) so the stage queue shows live progress.
  const bakeFile = useCallback(async (file: File, id: string, extras?: File[], profile?: string) => {
    const isU = file.name.toLowerCase().endsWith('.uasset')
    setAssets((a) => a.map((x) => (x.id === id ? { ...x, status: isU ? 'converting' : 'baking' } : x)))
    try {
      const pap = await bake(file, { ...bakeOpts(profile), extras })
      setAssets((a) => a.map((x) => (x.id === id ? { ...x, pap, status: 'ok' } : x)))
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e)
      setAssets((a) => a.map((x) => (x.id === id ? { ...x, status: 'error', error: msg } : x)))
    }
  }, [bakeOpts])

  // turn dropped files into queued assets (meshes become assets; .bin/textures ride
  // along as sidecars for any .gltf in the same drop). Profile is left unset so an
  // untouched mesh follows the live "Default profile"; picking one per mesh locks it.
  const makeAssets = useCallback((files: File[]): Asset[] => {
    const meshFiles = files.filter((f) => /\.(obj|glb|gltf|stl|uasset)$/i.test(f.name))
    const sidecars = files.filter((f) => !/\.(obj|glb|gltf|stl|uasset)$/i.test(f.name))
    return meshFiles.map((f): Asset => ({
      id: `${f.name.replace(/\.[^.]+$/, '')}-${Math.random().toString(36).slice(2, 6)}`,
      name: f.name, file: f, status: 'queued',
      extras: f.name.toLowerCase().endsWith('.gltf') ? sidecars : undefined,
    }))
  }, [])

  // Bake a batch of queued assets (each at its own profile). .uasset files convert in
  // ONE Unreal boot, then bake from their tokens; meshes bake directly.
  const bakeBatch = useCallback(async (items: Asset[]) => {
    const mark = (id: string, patch: Partial<Asset>) =>
      setAssets((a) => a.map((x) => (x.id === id ? { ...x, ...patch } : x)))
    const uassets = items.filter((x) => x.name.toLowerCase().endsWith('.uasset'))
    const meshes = items.filter((x) => !x.name.toLowerCase().endsWith('.uasset'))
    if (uassets.length) {
      uassets.forEach((u) => mark(u.id, { status: 'converting' }))
      try {
        const results = await convertUassets(uassets.map((u) => u.file!))
        const byName = new Map(results.map((r) => [r.name, r]))
        for (const u of uassets) {
          const res = byName.get(u.name)
          if (!res?.ok || !res.token) { mark(u.id, { status: 'error', error: 'Unreal export failed' }); continue }
          mark(u.id, { status: 'baking' })
          try { mark(u.id, { pap: await bakeCached(res.token, bakeOpts(u.profile)), status: 'ok' }) }
          catch (e) { mark(u.id, { status: 'error', error: e instanceof Error ? e.message : String(e) }) }
        }
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e)
        uassets.forEach((u) => mark(u.id, { status: 'error', error: msg }))
      }
    }
    for (const x of meshes) await bakeFile(x.file!, x.id, x.extras, x.profile)
  }, [bakeFile, bakeOpts])

  // Stage: drop only queues (so the user can pick a per-mesh profile before baking).
  const onStageAdd = useCallback((files: File[]) => {
    const added = makeAssets(files)
    if (!added.length) return
    setAssets((a) => [...a, ...added])
    setSel((s) => s ?? added[0]?.id ?? null)
  }, [makeAssets])

  // Stage "Bake" button: bake every still-queued mesh at its chosen profile.
  const onBakeQueued = useCallback(async () => {
    // bake everything not yet baked: freshly queued AND previously-errored (retry)
    const pending = assets.filter((a) => (a.status === 'queued' || a.status === 'error') && a.file)
    if (pending.length) await bakeBatch(pending)
  }, [assets, bakeBatch])

  // Editor contexts (viewport drop, menubar/library import): add AND bake immediately.
  const onAddFiles = useCallback(async (files: File[]) => {
    const added = makeAssets(files)
    if (!added.length) return
    setAssets((a) => [...a, ...added])
    setSel((s) => s ?? added[0]?.id ?? null)
    await bakeBatch(added)
  }, [makeAssets, bakeBatch])


  const objId = selected?.pap?.asset_id ?? null

  // Placement rotation (euler° in XYZ order) → unit quaternion [x,y,z,w]. The
  // backend gates (stability, collision, constraints) orient the asset by this, so
  // rotating the body changes its support footprint and CoM projection. glTF/glb are
  // Y-up by spec but the gates assume canonical Z-up, so we fold in a +90°-about-X
  // base rotation (Y→Z) — the same upright transform the viewport applies. Without it
  // a centred upright asset reads its height as a sideways CoM offset and the gate
  // wrongly suggests an XY repair.
  const quat = useCallback((r: number[]): number[] => {
    const h = Math.PI / 360 // deg → rad, halved for the half-angle
    const cx = Math.cos(r[0] * h), sx = Math.sin(r[0] * h)
    const cy = Math.cos(r[1] * h), sy = Math.sin(r[1] * h)
    const cz = Math.cos(r[2] * h), sz = Math.sin(r[2] * h)
    const qUser = [
      sx * cy * cz + cx * sy * sz,
      cx * sy * cz - sx * cy * sz,
      cx * cy * sz + sx * sy * cz,
      cx * cy * cz - sx * sy * sz,
    ]
    const yup = /\.(gltf|glb)$/i.test(selected?.name ?? '')
    if (!yup) return qUser
    const s = Math.SQRT1_2 // +90° about X as a quaternion: [√½, 0, 0, √½]
    return qmul(qUser, [s, 0, 0, s])
  }, [selected?.name])

  const scaleVec = useCallback(() => [scale, scale, scale], [scale])

  const onValidate = useCallback(async () => {
    if (!objId) return
    setBusy(true)
    try { setVerdict(await validate(objId, pos, quat(rot), scaleVec(), freeStanding)) } finally { setBusy(false) }
  }, [objId, pos, rot, quat, scaleVec, freeStanding])

  const onRepair = useCallback(async () => {
    if (!objId) return
    setBusy(true)
    try {
      const tf = await repair(objId, pos, quat(rot), scaleVec())
      const rounded = tf.pos.map((v) => Math.round(v * 1000) / 1000) // mm precision, no e-notation
      setPos(rounded)
      setVerdict(await validate(objId, rounded, tf.quat, scaleVec(), freeStanding))
    } finally { setBusy(false) }
  }, [objId, pos, rot, quat, scaleVec, freeStanding])

  const onCommit = useCallback(async () => {
    if (!objId) return
    setBusy(true)
    try { await commit(objId, pos, quat(rot), scaleVec()) } finally { setBusy(false) }
  }, [objId, pos, rot, quat, scaleVec])

  // material-confirm loop: re-bake the selected mesh with the confirmed per-part
  // materials (now they drive physics) and lock them into the PAP.
  const onConfirmMaterials = useCallback(async (materials: Record<string, string>) => {
    if (!selected?.file) return
    setBusy(true)
    try {
      const pap = await bake(selected.file, { materials, ...bakeOpts(selected.profile), extras: selected.extras })
      setAssets((a) => a.map((x) => (x.id === selected.id ? { ...x, pap, status: 'ok' } : x)))
    } finally { setBusy(false) }
  }, [selected, bakeOpts])

  // Manual override of baked physics (mass / volume / CoM). Mutates the selected
  // asset's PAP so the viewport (CoM marker, plumb, force view) updates live.
  const onEditPap = useCallback((patch: { physical?: Partial<PAP['physical']>; geometry?: Partial<PAP['geometry']> }) => {
    setAssets((a) => a.map((x) => (x.id === sel && x.pap)
      ? { ...x, pap: {
          ...x.pap,
          physical: patch.physical ? { ...x.pap.physical, ...patch.physical } : x.pap.physical,
          geometry: patch.geometry ? { ...x.pap.geometry, ...patch.geometry } : x.pap.geometry,
        } }
      : x))
  }, [sel])

  // Closure: two ways to seal an open mesh — one-click AUTO hole-fill, or the MANUAL
  // plane tool. Both re-bake and report a result card with before→after mass/volume.
  const [capping, setCapping] = useState(false)
  const [capResult, setCapResult] = useState<CapResult | null>(null)
  const onStartCap = useCallback(() => { setCapResult(null); setCapping(true) }, [])
  const errResult = (before: PAP | undefined, mode: 'auto' | 'manual', e: unknown): CapResult => {
    const m = before?.physical.mass_kg ?? 0, v = before?.geometry.volume_m3 ?? 0
    return { status: 'error', mode, before: { mass: m, vol: v }, after: { mass: m, vol: v },
      watertight: !!before?.geometry.watertight, message: e instanceof Error ? e.message : String(e) }
  }
  const onApplyCap = useCallback(async (plane: CapPlane) => {
    if (!selected?.file) { setCapping(false); return }
    const before = selected.pap
    setBusy(true)
    try {
      const pap = await bake(selected.file, { capPlane: plane, profile: bakeOpts(selected.profile).profile, extras: selected.extras })
      setAssets((a) => a.map((x) => (x.id === selected.id ? { ...x, pap, status: 'ok' } : x)))
      setCapResult(classifyCap(before, pap, 'manual'))
    } catch (e) {
      setCapResult(errResult(before, 'manual', e))
    } finally { setBusy(false); setCapping(false) }
  }, [selected, bakeOpts])
  const onAutoFill = useCallback(async () => {
    if (!selected?.file) return
    const before = selected.pap
    setCapResult(null); setCapping(false); setBusy(true)
    try {
      const pap = await bake(selected.file, { cap: true, profile: bakeOpts(selected.profile).profile, extras: selected.extras })
      setAssets((a) => a.map((x) => (x.id === selected.id ? { ...x, pap, status: 'ok' } : x)))
      setCapResult(classifyCap(before, pap, 'auto'))
    } catch (e) {
      setCapResult(errResult(before, 'auto', e))
    } finally { setBusy(false) }
  }, [selected, bakeOpts])
  useEffect(() => { setCapping(false); setCapResult(null) }, [sel])  // reset cap state on asset change

  // Project save/open: bundle the .wdf semantics AND the real model files in one place.
  const onSaveProject = useCallback(async (name: string) => {
    const records: ProjectAsset[] = []
    const files: { key: string; file: File }[] = []
    for (const a of assets) {
      if (!a.file) continue   // declared-only assets (from a .wdf) carry no model file
      const all = [a.file, ...(a.extras ?? [])]
      records.push({ id: a.id, name: a.name, main: a.file.name, files: all.map((f) => f.name),
        profile: a.profile ?? a.pap?.profile, masks: a.pap?.parts, pap: a.pap })
      for (const f of all) files.push({ key: `${a.id}__${f.name}`, file: f })
    }
    if (!records.length) { alert('Nothing to save yet. Import and bake a mesh first.'); return }
    await saveProject(name, records, files)
    setProjectName(name)
    setRecent(addRecent(name))
  }, [assets])
  const onOpenProject = useCallback(async (name: string) => {
    const { manifest } = await openProjectData(name)
    const restored: Asset[] = []
    for (const rec of manifest.assets) {
      const fetched = await Promise.all(rec.files.map((fn) => fetchProjectFile(name, rec.id, fn)))
      const main = fetched.find((f) => f.name === rec.main) ?? fetched[0]
      const extras = fetched.filter((f) => f !== main)
      restored.push({ id: rec.id, name: rec.name, file: main, extras, pap: rec.pap,
        profile: rec.profile, status: rec.pap ? 'ok' : 'queued' })
    }
    setWdf(null)
    setVerdict(null); setCapResult(null); setSweptGeo(null)
    setPos([0, 0, 0]); setRot([0, 0, 0]); setScale(1)
    setAssets(restored)
    setSel(restored[0]?.id ?? null)
    setProjectName(name)
    setRecent(addRecent(name))
    setScreen('editor')
  }, [])

  // Open a Recent entry: actually load the saved project. If it's gone (deleted /
  // different machine), drop the stale entry instead of failing silently.
  const openRecent = useCallback(async (name: string) => {
    try { await onOpenProject(name) }
    catch (e) {
      console.error('open recent failed', e)
      setRecent(removeRecent(name))
      alert(`Couldn't open "${name}". It may have been deleted.`)
    }
  }, [onOpenProject])

  const canPlace = selected?.status === 'ok' && !!objId

  if (screen === 'splash') {
    return (
      <>
        <IconDefs />
        <Splash recent={recent} onNew={startNew}
          onOpen={onOpenFile} onOpenRecent={(e) => openRecent(e.name)} />
      </>
    )
  }

  if (screen === 'stage') {
    return (
      <>
        <IconDefs />
        <Stage assets={assets} settings={settings} setSettings={setSettings}
          onAddFiles={onStageAdd} onBake={onBakeQueued} onEnter={() => setScreen('editor')}
          onUpdateAsset={(id, patch) => setAssets((a) => a.map((x) => (x.id === id ? { ...x, ...patch } : x)))}
          onRemove={(id) => { setAssets((a) => a.filter((x) => x.id !== id)); setSel((s) => (s === id ? null : s)) }}
          ueAvailable={ueAvailable} />
      </>
    )
  }

  return (
    <div className="app">
      <IconDefs />

      <Menubar
        projectName={projectName ? `${projectName}` : wdf?.scene ? `${wdf.scene.name}.wdf` : 'untitled'}
        assetCount={assets.length}
        onNew={startNew}
        onOpenWdf={onOpenFile}
        onImport={onAddFiles}
        onSaveProject={onSaveProject}
        onOpenProject={openRecent}
        panels={panels}
        onTogglePanel={togglePanel}
      />

      {panels.gates && (
        <GateStack verdict={verdict}
          {...(canPlace ? { pos, setPos, rot, setRot, busy, onValidate, onRepair, onCommit, freeStanding, setFreeStanding } : {})} />
      )}
      {wdf?.scene && <LawsBand scene={wdf.scene} />}

      <div className="row" style={{ '--aw': `${leftW}px`, '--pw': `${rightW}px` } as React.CSSProperties}>
        {panels.assets && (
          <>
            <AssetsPanel assets={assets} selected={sel} onSelect={setSel} onImport={onAddFiles}
              onDelete={(id) => { setAssets((a) => a.filter((x) => x.id !== id)); setSel((s) => (s === id ? null : s)) }}
              onUpdate={(id, patch) => setAssets((a) => a.map((x) => (x.id === id ? { ...x, ...patch } : x)))} />
            <div className="col-resize" onPointerDown={startColResize('l')} role="separator" aria-orientation="vertical" title="Drag to resize" />
          </>
        )}
        <Viewport name={selected?.name ?? ''} file={selected?.file} extras={selected?.extras}
          pap={selected?.pap ?? null} pos={pos} rot={rot} scale={scale} verdict={verdict} status={selected?.status}
          swept={sweptGeo} onDropFiles={onAddFiles} capping={capping} onApplyCap={onApplyCap}
          onExitCap={() => setCapping(false)} busy={busy}
          capResult={capResult} onCapAgain={onStartCap} onDismissCap={() => setCapResult(null)} />
        {panels.properties && (
          <>
            <div className="col-resize" onPointerDown={startColResize('r')} role="separator" aria-orientation="vertical" title="Drag to resize" />
            <Properties pap={selected?.pap ?? null}
              onConfirm={onConfirmMaterials} onCapOpenings={onStartCap} onAutoFill={onAutoFill} capping={capping}
              onEditPap={onEditPap} busy={busy} declared={selected?.wdf}
              footer={selected?.pap ? <PlacementTool assetId={selected.pap.asset_id} obb={selected.pap.geometry.obb} /> : undefined}
              {...(canPlace ? { scale, onScale: setScale } : {})} />
          </>
        )}
      </div>

      {panels.nodeEditor && (
        <>
          <div
            className="resize-handle"
            onPointerDown={startResize}
            role="separator"
            aria-orientation="horizontal"
            title="Drag to resize the node editor"
          />
          <div className="nodeeditor" style={{ height: nodeH }}>
            <header>
              <Icon name="reach" /><span className="t">Node editor</span>
            </header>
            <div className="ne">
              <ReactFlowProvider>
                <Palette />
                <ConstraintGraph scene={scene} objects={objects} verdict={verdict} />
              </ReactFlowProvider>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
