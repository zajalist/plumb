import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { Icon } from './Icons'
import type { PAP, Part, Verdict } from './api'

const SAGE = 0x34c0ad, FAIL = 0xe0694f, IDLE = 0x5e676e, AMBER = 0xd9a84c
const SOLID = '#3a4348'

type Refs = {
  host: HTMLDivElement
  renderer: THREE.WebGLRenderer
  scene: THREE.Scene
  cam: THREE.PerspectiveCamera
  controls: OrbitControls     // user orbit / pan / zoom
  grid: THREE.GridHelper      // floor, scaled to the mesh
  meshHolder: THREE.Group       // placed assembly (moves with pos)
  parts: THREE.Group            // the per-part mask meshes
  partMats: THREE.MeshStandardMaterial[]
  footprint: THREE.LineLoop
  comDot: THREE.Mesh
  plumb: THREE.Line
  landing: THREE.Mesh
  raf: number
}

// Frame the camera + floor grid to the baked geometry so any mesh scale reads
// right (a 5 m statue and a 5 cm trinket both fill the view sensibly).
function frameToParts(r: Refs) {
  r.scene.updateMatrixWorld(true)
  const box = new THREE.Box3().setFromObject(r.parts)
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

function buildParts(group: THREE.Group, partList: Part[]): THREE.MeshStandardMaterial[] {
  while (group.children.length) {
    const c = group.children[0] as THREE.Mesh
    group.remove(c); c.geometry.dispose(); (c.material as THREE.Material).dispose()
  }
  const mats: THREE.MeshStandardMaterial[] = []
  for (const p of partList) {
    if (!p.verts?.length || !p.tris?.length) continue
    const geom = new THREE.BufferGeometry()
    geom.setAttribute('position', new THREE.BufferAttribute(new Float32Array(p.verts.flat()), 3))
    geom.setIndex(p.tris.flat())
    geom.computeVertexNormals()
    const mat = new THREE.MeshStandardMaterial({ color: p.color, roughness: 0.82, metalness: 0.05, flatShading: true })
    mat.userData.mask = p.color
    group.add(new THREE.Mesh(geom, mat))
    mats.push(mat)
  }
  return mats
}

/** Dark device stage: renders the baked masks (per-part convex hulls, each in its
 *  mask colour) + the verdict viz (CoM, plumb line, support footprint). Canonical
 *  is Z-up; the world group is tilted so Z reads up. */
export function Viewport({ name, pap, pos, verdict, status }: {
  name: string; pap: PAP | null; pos: number[]; verdict: Verdict | null
  status?: 'queued' | 'converting' | 'baking' | 'ok' | 'error' | 'declared'
}) {
  const hostRef = useRef<HTMLDivElement>(null)
  const refs = useRef<Refs | null>(null)
  const posRef = useRef(pos); posRef.current = pos   // latest pos, without re-framing
  const [view, setView] = useState<'masks' | 'solid'>('masks')
  const hasParts = !!pap?.parts?.some((p) => p.verts?.length)

  const emptyMsg = hasParts ? null
    : status === 'baking' ? 'decomposing…'
    : status === 'converting' ? 'converting via Unreal…'
    : status === 'queued' ? 'queued…'
    : status === 'error' ? 'bake failed'
    : status === 'declared' ? 'declared asset — no baked geometry'
    : pap ? 'no masks'
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
    host.appendChild(renderer.domElement)

    scene.add(new THREE.HemisphereLight(0xc8d0d4, 0x0e1113, 1.0))
    const key = new THREE.DirectionalLight(0xffffff, 0.55); key.position.set(2, 5, 3); scene.add(key)

    const world = new THREE.Group(); world.rotation.x = -Math.PI / 2; scene.add(world)
    const grid = new THREE.GridHelper(1.6, 16, 0x223035, 0x161b1e)
    grid.rotation.x = Math.PI / 2; world.add(grid)

    const meshHolder = new THREE.Group(); world.add(meshHolder)
    const parts = new THREE.Group(); meshHolder.add(parts)

    const footprint = new THREE.LineLoop(new THREE.BufferGeometry(), new THREE.LineBasicMaterial({ color: IDLE }))
    world.add(footprint)
    const comDot = new THREE.Mesh(new THREE.SphereGeometry(0.02, 16, 16), new THREE.MeshBasicMaterial({ color: AMBER }))
    comDot.visible = false; world.add(comDot)
    const plumb = new THREE.Line(new THREE.BufferGeometry(), new THREE.LineDashedMaterial({ color: IDLE, dashSize: 0.03, gapSize: 0.02 }))
    plumb.visible = false; world.add(plumb)
    const landing = new THREE.Mesh(new THREE.RingGeometry(0.012, 0.022, 20), new THREE.MeshBasicMaterial({ color: IDLE, side: THREE.DoubleSide }))
    landing.rotation.x = -Math.PI / 2; landing.visible = false; world.add(landing)

    // user camera: drag to orbit, scroll to zoom, right-drag to pan. Idle auto-spin
    // until the user grabs it.
    cam.position.set(1.1, 0.85, 1.1)
    const controls = new OrbitControls(cam, renderer.domElement)
    controls.enableDamping = true
    controls.dampingFactor = 0.08
    controls.autoRotate = true
    controls.autoRotateSpeed = 0.9
    controls.target.set(0, 0.3, 0)
    controls.addEventListener('start', () => { controls.autoRotate = false })

    const tick = () => {
      controls.update()
      renderer.render(scene, cam)
      r.raf = requestAnimationFrame(tick)
    }
    const ro = new ResizeObserver(() => {
      const nw = host.clientWidth, nh = host.clientHeight
      if (nw && nh) { cam.aspect = nw / nh; cam.updateProjectionMatrix(); renderer.setSize(nw, nh) }
    })
    ro.observe(host)

    const r: Refs = { host, renderer, scene, cam, controls, grid, meshHolder, parts, partMats: [], footprint, comDot, plumb, landing, raf: 0 }
    refs.current = r
    tick()

    return () => {
      cancelAnimationFrame(r.raf); ro.disconnect(); controls.dispose(); renderer.dispose()
      if (renderer.domElement.parentNode === host) host.removeChild(renderer.domElement)
      refs.current = null
    }
  }, [])

  // ---- (re)build mask meshes + frame the camera when the baked parts change ----
  useEffect(() => {
    const r = refs.current
    if (!r) return
    const p = posRef.current
    r.meshHolder.position.set(p[0] ?? 0, p[1] ?? 0, p[2] ?? 0)
    r.partMats = buildParts(r.parts, pap?.parts ?? [])
    frameToParts(r)
  }, [pap?.asset_id, pap?.parts])

  // ---- recolour on masks/solid toggle ----
  useEffect(() => {
    const r = refs.current
    if (!r) return
    for (const m of r.partMats) m.color.set(view === 'masks' ? (m.userData.mask as string) : SOLID)
  }, [view, pap?.asset_id, pap?.parts])

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
        <div className="t"><Icon name="aperture" /><span>Viewport — {name || '—'}</span></div>
        {hasParts && (
          <div className="vptoggle">
            <button className={view === 'masks' ? 'on' : ''} onClick={() => setView('masks')}>masks</button>
            <button className={view === 'solid' ? 'on' : ''} onClick={() => setView('solid')}>solid</button>
          </div>
        )}
      </header>
      <div className="stage">
        <div className="crop tl" /><div className="crop tr" /><div className="crop bl" /><div className="crop br" />
        <div ref={hostRef} style={{ position: 'absolute', inset: 0 }} />
        {emptyMsg && <div className="emptyvp">{emptyMsg}</div>}
        <div className="axis">Z↑ X→<br />m · kg</div>
      </div>
    </section>
  )
}
