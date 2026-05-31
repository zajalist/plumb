import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'
import { OBJLoader } from 'three/addons/loaders/OBJLoader.js'
import { Icon } from './Icons'
import type { PAP, Part, Verdict } from './api'

const SAGE = 0x34c0ad, FAIL = 0xe0694f, IDLE = 0x5e676e, AMBER = 0xd9a84c
const SOLID = '#3a4348'
// distinct, muted mask colours (one per material group / part)
const MASK_PALETTE = ['#34C0AD', '#D9A84C', '#7E8AA0', '#E0694F', '#6E8B7A', '#A088B0', '#B58A5A', '#7C8AA0']

type Group = { meshes: THREE.Mesh[]; orig: THREE.Material[]; color: string; name: string }
type Refs = {
  host: HTMLDivElement
  renderer: THREE.WebGLRenderer
  scene: THREE.Scene
  cam: THREE.PerspectiveCamera
  controls: OrbitControls
  grid: THREE.GridHelper
  meshHolder: THREE.Group     // placed assembly (moves with pos)
  content: THREE.Group        // the loaded model OR convex-part masks
  inertiaGroup: THREE.Group   // inertia ellipsoid + axes + gravity (physics view)
  groups: Group[]             // material groups (or parts) for the masks view
  urls: string[]              // blob URLs to revoke
  footprint: THREE.LineLoop
  comDot: THREE.Mesh
  plumb: THREE.Line
  landing: THREE.Mesh
  setCam: (v: 'recenter' | 'top' | 'front' | 'side' | 'persp') => void
  raf: number
}

// Group the loaded model's meshes by material so the masks view can colour each
// material region (trunk / branch / leaves …) distinctly — these are the real masks.
function buildGroups(root: THREE.Object3D): Group[] {
  const byMat = new Map<string, Group>()
  let order = 0
  root.traverse((o) => {
    const m = o as THREE.Mesh
    if (!m.isMesh) return
    const mat = m.material as THREE.Material & { name?: string }
    const key = mat?.name || `mat_${order}`
    let g = byMat.get(key)
    if (!g) { g = { meshes: [], orig: [], color: MASK_PALETTE[order++ % MASK_PALETTE.length], name: key }; byMat.set(key, g) }
    g.meshes.push(m)
    g.orig.push(m.material as THREE.Material)
  })
  return [...byMat.values()]
}

function applyView(groups: Group[], view: 'textured' | 'masks') {
  for (const g of groups) {
    g.meshes.forEach((m, i) => {
      if (view === 'masks') {
        const mm = m.userData.maskMat ||= new THREE.MeshStandardMaterial({ color: g.color, roughness: 0.85, metalness: 0.04, flatShading: false })
        m.material = mm
      } else {
        m.material = g.orig[i]
      }
    })
  }
}

function clearContent(r: Refs) {
  // NB: we deliberately do NOT revoke the texture/.bin blob URLs here — GLTFLoader
  // loads textures asynchronously, and revoking an in-flight blob (e.g. under React
  // StrictMode's double-invoke) makes every texture fail with ERR_FILE_NOT_FOUND.
  // The handful of blob URLs per load is a bounded leak the browser frees on unload.
  for (const g of r.groups) g.meshes.forEach((m) => (m.userData.maskMat as THREE.Material | undefined)?.dispose())
  r.groups = []
  while (r.content.children.length) {
    const c = r.content.children[0]
    r.content.remove(c)
    c.traverse?.((o) => { const m = o as THREE.Mesh; m.geometry?.dispose?.() })
  }
}

// Frame camera + floor grid to the content so any mesh scale reads right.
function frame(r: Refs) {
  r.scene.updateMatrixWorld(true)
  const box = new THREE.Box3().setFromObject(r.content)
  if (box.isEmpty()) return
  const center = box.getCenter(new THREE.Vector3())
  const radius = Math.max(box.getBoundingSphere(new THREE.Sphere()).radius, 1e-3)
  r.grid.scale.setScalar(Math.min(80, Math.max(0.4, radius * 2.4)) / 1.6)
  const fov = (r.cam.fov * Math.PI) / 180
  const dist = (radius / Math.sin(fov / 2)) * 1.35
  r.controls.target.copy(center)
  r.cam.position.copy(center).addScaledVector(new THREE.Vector3(1, 0.7, 1).normalize(), dist)
  r.cam.near = Math.max(1e-3, radius / 100)
  r.cam.far = radius * 200 + 10
  r.cam.updateProjectionMatrix()
  r.controls.minDistance = radius * 0.4
  r.controls.maxDistance = radius * 30
  r.controls.update()
}

// Load a real model client-side (textures + materials intact). .gltf resolves its
// sibling .bin / textures from the dropped sidecar files via blob URLs.
async function loadModel(file: File, extras: File[], urls: string[]): Promise<THREE.Object3D> {
  const ext = (file.name.split('.').pop() || '').toLowerCase()
  if (ext === 'obj') return new OBJLoader().parse(await file.text())
  const manager = new THREE.LoadingManager()
  const map = new Map<string, string>()
  for (const f of [file, ...extras]) { const u = URL.createObjectURL(f); urls.push(u); map.set(f.name.toLowerCase(), u) }
  manager.setURLModifier((url) => {
    const base = decodeURIComponent((url.split('/').pop() || url)).toLowerCase()
    return map.get(base) ?? url
  })
  const loader = new GLTFLoader(manager)
  // glTF is Y-up by spec; our canonical world is Z-up — rotate the model +90° about
  // X so +Y(model) → +Z(world) and it stands upright.
  const upright = (g: { scene: THREE.Object3D }) => { g.scene.rotation.x = Math.PI / 2; return g.scene }
  if (ext === 'glb') {
    const buf = await file.arrayBuffer()
    return await new Promise((res, rej) => loader.parse(buf, '', (g) => res(upright(g)), rej))
  }
  const text = await file.text()
  return await new Promise((res, rej) => loader.parse(text, '', (g) => res(upright(g)), rej))
}

// Build convex-part masks from the bake (fallback when there's no client file, e.g.
// a .uasset converted server-side).
function buildPartGroup(content: THREE.Group, parts: Part[]): Group[] {
  const groups: Group[] = []
  for (const p of parts) {
    if (!p.verts?.length || !p.tris?.length) continue
    const geom = new THREE.BufferGeometry()
    geom.setAttribute('position', new THREE.BufferAttribute(new Float32Array(p.verts.flat()), 3))
    geom.setIndex(p.tris.flat())
    geom.computeVertexNormals()
    const orig = new THREE.MeshStandardMaterial({ color: SOLID, roughness: 0.85, metalness: 0.04 })
    const mesh = new THREE.Mesh(geom, orig)
    content.add(mesh)
    groups.push({ meshes: [mesh], orig: [orig], color: p.color, name: p.id })
  }
  return groups
}

// Jacobi eigendecomposition of a symmetric 3×3 (for the inertia tensor). Returns
// principal moments (values) + principal axes (vectors, as columns).
function symEig3(M: number[][]): { values: number[]; vectors: number[][] } {
  const a = M.map((row) => row.slice())
  const v = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
  for (let iter = 0; iter < 60; iter++) {
    let p = 0, q = 1, max = Math.abs(a[0][1])
    if (Math.abs(a[0][2]) > max) { max = Math.abs(a[0][2]); p = 0; q = 2 }
    if (Math.abs(a[1][2]) > max) { max = Math.abs(a[1][2]); p = 1; q = 2 }
    if (max < 1e-14) break
    const phi = 0.5 * Math.atan2(2 * a[p][q], a[q][q] - a[p][p])
    const c = Math.cos(phi), s = Math.sin(phi)
    for (let k = 0; k < 3; k++) { const kp = a[k][p], kq = a[k][q]; a[k][p] = c * kp - s * kq; a[k][q] = s * kp + c * kq }
    for (let k = 0; k < 3; k++) { const pk = a[p][k], qk = a[q][k]; a[p][k] = c * pk - s * qk; a[q][k] = s * pk + c * qk }
    for (let k = 0; k < 3; k++) { const kp = v[k][p], kq = v[k][q]; v[k][p] = c * kp - s * kq; v[k][q] = s * kp + c * kq }
  }
  return {
    values: [a[0][0], a[1][1], a[2][2]],
    vectors: [[v[0][0], v[1][0], v[2][0]], [v[0][1], v[1][1], v[2][1]], [v[0][2], v[1][2], v[2][2]]],
  }
}

// The mass distribution made visible: the equivalent-inertia ellipsoid at the CoM
// (semi-axes solved from the inertia tensor), its principal axes, and the gravity
// vector. Long axis = mass spread that way; short axis = compact / hard to topple.
function buildInertia(group: THREE.Group, pap: PAP) {
  while (group.children.length) {
    const c = group.children[0] as THREE.Mesh
    group.remove(c); c.geometry?.dispose?.(); (c.material as THREE.Material)?.dispose?.()
  }
  const I = pap.physical.inertia, m = pap.physical.mass_kg, com = pap.physical.com ?? [0, 0, 0]
  const ok = Array.isArray(I) && I.length === 3 && I.every((r) => r?.length === 3) && I.flat().some((x) => Math.abs(x) > 1e-9)
  if (!ok || m <= 0) return
  const { values, vectors } = symEig3(I)
  const S = 2.5 * (values[0] + values[1] + values[2]) / m
  const semi = [0, 1, 2].map((i) => Math.sqrt(Math.max(1e-5, S - (5 * values[i]) / m)))
  const span = Math.max(...semi, 1e-3)

  const ell = new THREE.Mesh(
    new THREE.SphereGeometry(1, 36, 24),
    new THREE.MeshStandardMaterial({ color: 0x34c0ad, transparent: true, opacity: 0.26, roughness: 0.45, metalness: 0.1, side: THREE.DoubleSide, depthWrite: false }),
  )
  ell.scale.set(semi[0], semi[1], semi[2])
  ell.position.set(com[0], com[1], com[2])
  const e0 = new THREE.Vector3(...vectors[0]).normalize()
  const e1 = new THREE.Vector3(...vectors[1]).normalize()
  const e2 = new THREE.Vector3(...vectors[2]).normalize()
  ell.quaternion.setFromRotationMatrix(new THREE.Matrix4().makeBasis(e0, e1, e2))
  group.add(ell)

  // principal axes
  const c0 = new THREE.Vector3(com[0], com[1], com[2])
  ;[[e0, semi[0]], [e1, semi[1]], [e2, semi[2]]].forEach(([dir, len]) => {
    group.add(new THREE.ArrowHelper(dir as THREE.Vector3, c0, (len as number) * 1.15, 0x9fb0b6, span * 0.12, span * 0.07))
  })
  // gravity (canonical down = -Z)
  group.add(new THREE.ArrowHelper(new THREE.Vector3(0, 0, -1), c0, span * 1.8, 0xD9A84C, span * 0.16, span * 0.09))
  // CoM marker
  const dot = new THREE.Mesh(new THREE.SphereGeometry(span * 0.06, 16, 16), new THREE.MeshBasicMaterial({ color: 0xE7EAEC }))
  dot.position.copy(c0); group.add(dot)
}

/** Dark device stage: renders the real textured model (materials/textures intact),
 *  with a textured ↔ masks toggle that colours each material group. Plus the verdict
 *  viz (CoM, plumb, support footprint). Canonical is Z-up; world tilted so Z reads up. */
export function Viewport({ name, file, extras, pap, pos, verdict, status, onDropFiles }: {
  name: string; file?: File | null; extras?: File[]
  pap: PAP | null; pos: number[]; verdict: Verdict | null
  status?: 'queued' | 'converting' | 'baking' | 'ok' | 'error' | 'declared'
  onDropFiles?: (files: File[]) => void
}) {
  const hostRef = useRef<HTMLDivElement>(null)
  const refs = useRef<Refs | null>(null)
  const posRef = useRef(pos); posRef.current = pos
  const [view, setView] = useState<'textured' | 'masks' | 'inertia'>('textured')
  const [hasContent, setHasContent] = useState(false)
  const [dropping, setDropping] = useState(false)

  const emptyMsg = hasContent ? null
    : status === 'baking' ? 'decomposing…'
    : status === 'converting' ? 'converting via Unreal…'
    : status === 'queued' ? 'queued…'
    : status === 'error' ? 'bake failed'
    : status === 'declared' ? 'declared asset · no baked geometry'
    : (file || pap) ? 'loading…'
    : 'no asset selected'

  // ---- one-time scene setup ----
  useEffect(() => {
    const host = hostRef.current
    if (!host) return
    const w = host.clientWidth || 600, h = host.clientHeight || 360
    const scene = new THREE.Scene()
    scene.background = new THREE.Color('#0A0C0E')
    const cam = new THREE.PerspectiveCamera(38, w / h, 0.01, 100)
    const renderer = new THREE.WebGLRenderer({ antialias: true })
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2))
    renderer.setSize(w, h)
    renderer.outputColorSpace = THREE.SRGBColorSpace
    host.appendChild(renderer.domElement)

    scene.add(new THREE.HemisphereLight(0xc8d0d4, 0x0e1113, 1.1))
    const key = new THREE.DirectionalLight(0xffffff, 1.2); key.position.set(2, 5, 3); scene.add(key)
    const fill = new THREE.DirectionalLight(0xc8d0d4, 0.4); fill.position.set(-3, 2, -2); scene.add(fill)

    const world = new THREE.Group(); world.rotation.x = -Math.PI / 2; scene.add(world)
    const grid = new THREE.GridHelper(1.6, 16, 0x223035, 0x161b1e)
    grid.rotation.x = Math.PI / 2; world.add(grid)
    const meshHolder = new THREE.Group(); world.add(meshHolder)
    const content = new THREE.Group(); meshHolder.add(content)
    const inertiaGroup = new THREE.Group(); inertiaGroup.visible = false; meshHolder.add(inertiaGroup)

    const footprint = new THREE.LineLoop(new THREE.BufferGeometry(), new THREE.LineBasicMaterial({ color: IDLE }))
    world.add(footprint)
    const comDot = new THREE.Mesh(new THREE.SphereGeometry(0.02, 16, 16), new THREE.MeshBasicMaterial({ color: AMBER }))
    comDot.visible = false; world.add(comDot)
    const plumb = new THREE.Line(new THREE.BufferGeometry(), new THREE.LineDashedMaterial({ color: IDLE, dashSize: 0.03, gapSize: 0.02 }))
    plumb.visible = false; world.add(plumb)
    const landing = new THREE.Mesh(new THREE.RingGeometry(0.012, 0.022, 20), new THREE.MeshBasicMaterial({ color: IDLE, side: THREE.DoubleSide }))
    landing.rotation.x = -Math.PI / 2; landing.visible = false; world.add(landing)

    cam.position.set(1.1, 0.85, 1.1)
    const controls = new OrbitControls(cam, renderer.domElement)
    controls.enableDamping = true; controls.dampingFactor = 0.08
    controls.autoRotate = true; controls.autoRotateSpeed = 0.9
    controls.target.set(0, 0.3, 0)
    controls.addEventListener('start', () => { controls.autoRotate = false })

    // corner orientation gizmo (canonical Z-up · X red / Y green / Z blue)
    const giz = new THREE.Scene()
    const gcam = new THREE.OrthographicCamera(-1.7, 1.7, 1.7, -1.7, 0.1, 10)
    const triad = new THREE.Group()
    const axis = (d: THREE.Vector3, c: number) => triad.add(new THREE.ArrowHelper(d, new THREE.Vector3(), 1, c, 0.32, 0.2))
    axis(new THREE.Vector3(1, 0, 0), 0xe0694f)
    axis(new THREE.Vector3(0, 1, 0), 0x6fbf73)
    axis(new THREE.Vector3(0, 0, 1), 0x5c8bd6)
    triad.quaternion.copy(world.quaternion)
    giz.add(triad)
    const _sz = new THREE.Vector2(), _dir = new THREE.Vector3()

    const tick = () => {
      controls.update()
      renderer.render(scene, cam)
      // overlay the axis gizmo in the bottom-left corner
      _dir.copy(cam.position).sub(controls.target).normalize().multiplyScalar(4)
      gcam.position.copy(_dir); gcam.up.copy(cam.up); gcam.lookAt(0, 0, 0)
      renderer.getSize(_sz)
      renderer.autoClear = false
      renderer.clearDepth()
      renderer.setViewport(12, 12, 78, 78)
      renderer.render(giz, gcam)
      renderer.setViewport(0, 0, _sz.x, _sz.y)
      renderer.autoClear = true
      r.raf = requestAnimationFrame(tick)
    }
    const ro = new ResizeObserver(() => {
      const nw = host.clientWidth, nh = host.clientHeight
      if (nw && nh) { cam.aspect = nw / nh; cam.updateProjectionMatrix(); renderer.setSize(nw, nh) }
    })
    ro.observe(host)

    // camera presets: frame the content from a canonical direction (or recenter)
    const VIEW_DIR: Record<string, [number, number, number]> = {
      top: [0, 1, 0.0001], front: [0, 0, 1], side: [1, 0, 0], persp: [1, 0.7, 1],
    }
    const setCam = (v: 'recenter' | 'top' | 'front' | 'side' | 'persp') => {
      controls.autoRotate = false
      scene.updateMatrixWorld(true)
      const box = new THREE.Box3().setFromObject(content)
      const center = box.isEmpty() ? new THREE.Vector3(0, 0.3, 0) : box.getCenter(new THREE.Vector3())
      const radius = box.isEmpty() ? 1 : Math.max(box.getBoundingSphere(new THREE.Sphere()).radius, 1e-3)
      const dir = v === 'recenter'
        ? new THREE.Vector3().subVectors(cam.position, controls.target).normalize()
        : new THREE.Vector3(...VIEW_DIR[v]).normalize()
      if (dir.lengthSq() < 1e-6) dir.set(1, 0.7, 1).normalize()
      const dist = (radius / Math.sin((cam.fov * Math.PI / 180) / 2)) * 1.35
      cam.up.set(0, v === 'top' ? 0 : 1, v === 'top' ? -1 : 0)
      controls.target.copy(center)
      cam.position.copy(center).addScaledVector(dir, dist)
      cam.lookAt(center)
      controls.update()
    }

    const r: Refs = { host, renderer, scene, cam, controls, grid, meshHolder, content, inertiaGroup, groups: [], urls: [], footprint, comDot, plumb, landing, setCam, raf: 0 }
    refs.current = r
    tick()
    return () => {
      cancelAnimationFrame(r.raf); ro.disconnect(); controls.dispose(); clearContent(r); renderer.dispose()
      if (renderer.domElement.parentNode === host) host.removeChild(renderer.domElement)
      refs.current = null
    }
  }, [])

  // ---- load content (real model if we have the file, else convex-part masks) ----
  useEffect(() => {
    const r = refs.current
    if (!r) return
    let cancelled = false
    const p = posRef.current
    r.meshHolder.position.set(p[0] ?? 0, p[1] ?? 0, p[2] ?? 0)
    clearContent(r)
    setHasContent(false)
    if (pap) buildInertia(r.inertiaGroup, pap)
    r.inertiaGroup.visible = view === 'inertia'

    if (file) {
      loadModel(file, extras ?? [], r.urls).then((model) => {
        if (cancelled || refs.current !== r) return
        r.content.add(model)
        r.groups = buildGroups(model)
        applyView(r.groups, view === 'masks' ? 'masks' : 'textured')
        frame(r)
        setHasContent(true)
      }).catch((e) => { if (!cancelled) console.error('model load failed', e) })
    } else if (pap?.parts?.some((pt) => pt.verts?.length)) {
      r.groups = buildPartGroup(r.content, pap.parts)
      applyView(r.groups, view === 'masks' ? 'masks' : 'textured')
      frame(r)
      setHasContent(true)
    }
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [file, extras, pap?.asset_id])

  // ---- recolour + inertia overlay on view toggle ----
  useEffect(() => {
    const r = refs.current
    if (!r) return
    applyView(r.groups, view === 'masks' ? 'masks' : 'textured')
    r.inertiaGroup.visible = view === 'inertia'
  }, [view, hasContent])

  // ---- placement + verdict viz ----
  useEffect(() => {
    const r = refs.current
    if (!r || !pap) return
    const com = pap.physical.com ?? [0, 0, 0]
    const hx = pap.geometry.obb?.[0] ?? 0.2, hy = pap.geometry.obb?.[1] ?? 0.2
    const wx = pos[0] + com[0], wy = pos[1] + com[1], wz = pos[2] + com[2]
    r.meshHolder.position.set(pos[0], pos[1], pos[2])
    r.footprint.geometry.setFromPoints([
      new THREE.Vector3(-hx, -hy, 0), new THREE.Vector3(hx, -hy, 0),
      new THREE.Vector3(hx, hy, 0), new THREE.Vector3(-hx, hy, 0),
    ])
    r.comDot.position.set(wx, wy, wz); r.comDot.visible = true
    r.plumb.geometry.setFromPoints([new THREE.Vector3(wx, wy, wz), new THREE.Vector3(wx, wy, 0)])
    ;(r.plumb as THREE.Line).computeLineDistances(); r.plumb.visible = true
    r.landing.position.set(wx, wy, 0.001); r.landing.visible = true
    const stab = verdict?.gates.find((g) => g.gate === 'stability')
    const col = stab ? (stab.ok === false ? FAIL : stab.ok === true ? SAGE : IDLE) : IDLE
    ;(r.footprint.material as THREE.LineBasicMaterial).color.setHex(col)
    ;(r.plumb.material as THREE.LineDashedMaterial).color.setHex(col)
    ;(r.landing.material as THREE.MeshBasicMaterial).color.setHex(col)
  }, [pos, verdict, pap])

  return (
    <section className="pane viewport">
      <header>
        <div className="t"><Icon name="aperture" /><span>Viewport{name ? ` · ${name}` : ''}</span></div>
        {hasContent && (
          <div className="vptoggle">
            <button className={view === 'textured' ? 'on' : ''} onClick={() => setView('textured')}>textured</button>
            <button className={view === 'masks' ? 'on' : ''} onClick={() => setView('masks')}>masks</button>
            <button className={view === 'inertia' ? 'on' : ''} onClick={() => setView('inertia')}>inertia</button>
          </div>
        )}
      </header>
      <div
        className={`stage${dropping ? ' dropping' : ''}`}
        onDragOver={onDropFiles ? (e) => { e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; if (!dropping) setDropping(true) } : undefined}
        onDragLeave={onDropFiles ? (e) => { if (e.currentTarget === e.target) setDropping(false) } : undefined}
        onDrop={onDropFiles ? (e) => {
          e.preventDefault(); setDropping(false)
          const files = Array.from(e.dataTransfer.files)
          if (files.length) onDropFiles(files)
        } : undefined}
      >
        <div className="cambar">
          <button title="Recenter / frame" onClick={() => refs.current?.setCam('recenter')}>⌖</button>
          <span className="cb-sep" />
          <button onClick={() => refs.current?.setCam('top')}>Top</button>
          <button onClick={() => refs.current?.setCam('front')}>Front</button>
          <button onClick={() => refs.current?.setCam('side')}>Side</button>
          <button onClick={() => refs.current?.setCam('persp')}>Persp</button>
        </div>
        <div className="crop tl" /><div className="crop tr" /><div className="crop bl" /><div className="crop br" />
        <div ref={hostRef} style={{ position: 'absolute', inset: 0 }} />
        {emptyMsg && <div className="emptyvp">{emptyMsg}</div>}
        {dropping && <div className="dropover"><Icon name="import" /><span>Drop to bake</span></div>}
      </div>
    </section>
  )
}
