import { useEffect, useRef } from 'react'
import * as THREE from 'three'
import { OBJLoader } from 'three/addons/loaders/OBJLoader.js'
import { Icon } from './Icons'
import type { PAP, Verdict } from './api'

const SAGE = 0x8e9a60, FAIL = 0xc16a4a, IDLE = 0x7c7868, AMBER = 0xc2a24e

type Refs = {
  host: HTMLDivElement
  renderer: THREE.WebGLRenderer
  scene: THREE.Scene
  cam: THREE.PerspectiveCamera
  meshHolder: THREE.Group   // the placed mesh (moves with pos)
  footprint: THREE.LineLoop // the support polygon at origin (anchored)
  comDot: THREE.Mesh        // centre of mass marker
  plumb: THREE.Line         // CoM -> ground
  landing: THREE.Mesh       // where the plumb hits the floor
  raf: number
}

/** Dark device stage: renders the placed mesh + the verdict viz (CoM, plumb line,
 *  support footprint). Canonical is Z-up; the world group is tilted so Z reads up. */
export function Viewport({ file, name, pap, pos, verdict }: {
  file: File | null; name: string; pap: PAP | null; pos: number[]; verdict: Verdict | null
}) {
  const hostRef = useRef<HTMLDivElement>(null)
  const refs = useRef<Refs | null>(null)

  // ---- setup + load mesh (only when the file changes) ----
  useEffect(() => {
    const host = hostRef.current
    if (!host || !file) return
    let disposed = false
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

    // canonical world (Z-up): tilt so canonical Z points up in the view.
    const world = new THREE.Group(); world.rotation.x = -Math.PI / 2; scene.add(world)

    // floor grid in the canonical XY plane (z=0)
    const grid = new THREE.GridHelper(1.6, 16, 0x23231b, 0x1c1c15)
    grid.rotation.x = Math.PI / 2; world.add(grid)

    const meshHolder = new THREE.Group(); world.add(meshHolder)
    const material = new THREE.MeshStandardMaterial({ color: '#586040', roughness: 0.85, metalness: 0.08, flatShading: true })
    file.text().then((txt) => {
      if (disposed) return
      try {
        const obj = new OBJLoader().parse(txt)
        obj.traverse((o: THREE.Object3D) => { const m = o as THREE.Mesh; if (m.isMesh) m.material = material })
        meshHolder.add(obj)
      } catch { /* leave empty */ }
    })

    // support footprint (anchored at origin), CoM dot, plumb line, landing ring
    const footprint = new THREE.LineLoop(
      new THREE.BufferGeometry(), new THREE.LineBasicMaterial({ color: IDLE }))
    world.add(footprint)
    const comDot = new THREE.Mesh(
      new THREE.SphereGeometry(0.02, 16, 16), new THREE.MeshBasicMaterial({ color: AMBER }))
    comDot.visible = false; world.add(comDot)
    const plumb = new THREE.Line(
      new THREE.BufferGeometry(), new THREE.LineDashedMaterial({ color: IDLE, dashSize: 0.03, gapSize: 0.02 }))
    plumb.visible = false; world.add(plumb)
    const landing = new THREE.Mesh(
      new THREE.RingGeometry(0.012, 0.022, 20), new THREE.MeshBasicMaterial({ color: IDLE, side: THREE.DoubleSide }))
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

    const r: Refs = { host, renderer, scene, cam, meshHolder, footprint, comDot, plumb, landing, raf: 0 }
    refs.current = r
    tick()

    return () => {
      disposed = true
      cancelAnimationFrame(r.raf); ro.disconnect(); renderer.dispose(); material.dispose()
      if (renderer.domElement.parentNode === host) host.removeChild(renderer.domElement)
      refs.current = null
    }
  }, [file])

  // ---- update placement + verdict viz (when pos / verdict / pap change) ----
  useEffect(() => {
    const r = refs.current
    if (!r || !pap) return
    const com = pap.physical.com ?? [0, 0, 0]
    const hx = pap.geometry.obb?.[0] ?? 0.2, hy = pap.geometry.obb?.[1] ?? 0.2
    const wx = pos[0] + com[0], wy = pos[1] + com[1], wz = pos[2] + com[2]

    r.meshHolder.position.set(pos[0], pos[1], pos[2])

    // footprint rectangle at origin (z=0) — the anchored support the CoM slides over
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
        <span className="mono" style={{ fontSize: 10, color: 'var(--ink4)' }}>orbit · frame</span>
      </header>
      <div className="stage">
        <div className="crop tl" /><div className="crop tr" /><div className="crop bl" /><div className="crop br" />
        <div ref={hostRef} style={{ position: 'absolute', inset: 0 }} />
        {!file && <div className="emptyvp">no asset selected</div>}
        <div className="axis">Z↑ X→<br />m · kg</div>
      </div>
    </section>
  )
}
