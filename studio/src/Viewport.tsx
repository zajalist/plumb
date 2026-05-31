import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { Icon } from './Icons'
import type { PAP, Part, Verdict } from './api'

const SAGE = 0x8e9a60, FAIL = 0xc16a4a, IDLE = 0x7c7868, AMBER = 0xc2a24e
const SOLID = '#586040'

type Refs = {
  host: HTMLDivElement
  renderer: THREE.WebGLRenderer
  scene: THREE.Scene
  cam: THREE.PerspectiveCamera
  meshHolder: THREE.Group       // placed assembly (moves with pos)
  parts: THREE.Group            // the per-part mask meshes
  partMats: THREE.MeshStandardMaterial[]
  footprint: THREE.LineLoop
  comDot: THREE.Mesh
  plumb: THREE.Line
  landing: THREE.Mesh
  raf: number
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
export function Viewport({ name, pap, pos, verdict }: {
  name: string; pap: PAP | null; pos: number[]; verdict: Verdict | null
}) {
  const hostRef = useRef<HTMLDivElement>(null)
  const refs = useRef<Refs | null>(null)
  const [view, setView] = useState<'masks' | 'solid'>('masks')
  const hasParts = !!pap?.parts?.some((p) => p.verts?.length)

  // ---- one-time scene setup ----
  useEffect(() => {
    const host = hostRef.current
    if (!host) return
    const w = host.clientWidth || 600, h = host.clientHeight || 360

    const scene = new THREE.Scene()
    scene.background = new THREE.Color('#100F0A')
    const cam = new THREE.PerspectiveCamera(38, w / h, 0.01, 100)
    const renderer = new THREE.WebGLRenderer({ antialias: true })
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2))
    renderer.setSize(w, h)
    host.appendChild(renderer.domElement)

    scene.add(new THREE.HemisphereLight(0xcfcab8, 0x141310, 1.0))
    const key = new THREE.DirectionalLight(0xffffff, 0.55); key.position.set(2, 5, 3); scene.add(key)

    const world = new THREE.Group(); world.rotation.x = -Math.PI / 2; scene.add(world)
    const grid = new THREE.GridHelper(1.6, 16, 0x23231b, 0x1c1c15)
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

    let angle = 0.6
    const tick = () => {
      angle += 0.0025
      cam.position.set(Math.sin(angle) * 1.7, 0.95, Math.cos(angle) * 1.7)
      cam.lookAt(0, 0.32, 0)
      renderer.render(scene, cam)
      r.raf = requestAnimationFrame(tick)
    }
    const ro = new ResizeObserver(() => {
      const nw = host.clientWidth, nh = host.clientHeight
      if (nw && nh) { cam.aspect = nw / nh; cam.updateProjectionMatrix(); renderer.setSize(nw, nh) }
    })
    ro.observe(host)

    const r: Refs = { host, renderer, scene, cam, meshHolder, parts, partMats: [], footprint, comDot, plumb, landing, raf: 0 }
    refs.current = r
    tick()

    return () => {
      cancelAnimationFrame(r.raf); ro.disconnect(); renderer.dispose()
      if (renderer.domElement.parentNode === host) host.removeChild(renderer.domElement)
      refs.current = null
    }
  }, [])

  // ---- (re)build mask meshes when the baked parts change ----
  useEffect(() => {
    const r = refs.current
    if (!r) return
    r.partMats = buildParts(r.parts, pap?.parts ?? [])
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
        {!hasParts && <div className="emptyvp">{pap ? 'declared asset — no geometry' : 'no asset selected'}</div>}
        <div className="axis">Z↑ X→<br />m · kg</div>
      </div>
    </section>
  )
}
