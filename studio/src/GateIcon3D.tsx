// Live 3D gate icons (the "icon pipeline") — one tiny Three.js scene per gate,
// rendered with the same engine as the viewport. Each shape is semantic:
//   collision   → two solids overlapping (clearance / penetration)
//   stability   → a plumb line + bob over a base (CoM over support — the brand)
//   constraints → two interlocked rings (relations that bind)
//   reach       → a routed path between waypoints (navmesh reachability)
//   commit      → an arrow dispatching into the engine
// The material tints to the gate's status colour. Degrades to an empty canvas
// where WebGL is unavailable (e.g. jsdom under test), so it never throws.
import { useEffect, useRef } from 'react'
import * as THREE from 'three'

export type GateShape = 'collision' | 'stability' | 'constraints' | 'reach' | 'commit'

function buildShape(shape: GateShape, color: string): THREE.Object3D {
  const mat = new THREE.MeshStandardMaterial({ color, metalness: 0.34, roughness: 0.3 })
  const m = (geo: THREE.BufferGeometry) => new THREE.Mesh(geo, mat)
  const g = new THREE.Group()

  if (shape === 'collision') {
    const a = m(new THREE.BoxGeometry(0.85, 0.85, 0.85)); a.position.set(-0.28, 0.1, 0.1); a.rotation.set(0.2, 0.3, 0)
    const b = m(new THREE.BoxGeometry(0.85, 0.85, 0.85)); b.position.set(0.28, -0.1, -0.1); b.rotation.set(0.1, -0.4, 0.1)
    g.add(a, b)
  } else if (shape === 'stability') {
    const base = m(new THREE.CylinderGeometry(0.42, 0.5, 0.18, 32)); base.position.y = -0.62
    const line = m(new THREE.CylinderGeometry(0.025, 0.025, 0.95, 8)); line.position.y = 0.05
    const bob = m(new THREE.ConeGeometry(0.2, 0.42, 24)); bob.rotation.x = Math.PI; bob.position.y = -0.42
    const top = m(new THREE.SphereGeometry(0.08, 16, 16)); top.position.y = 0.54
    g.add(base, line, bob, top)
  } else if (shape === 'constraints') {
    const r1 = m(new THREE.TorusGeometry(0.45, 0.15, 20, 44)); r1.position.x = -0.26
    const r2 = m(new THREE.TorusGeometry(0.45, 0.15, 20, 44)); r2.position.x = 0.26; r2.rotation.y = Math.PI / 2
    g.add(r1, r2)
  } else if (shape === 'reach') {
    const pts = [new THREE.Vector3(-0.7, -0.5, 0), new THREE.Vector3(-0.1, 0.1, 0.2), new THREE.Vector3(0.45, -0.1, -0.2), new THREE.Vector3(0.75, 0.55, 0)]
    const tube = m(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 40, 0.07, 10, false))
    g.add(tube)
    for (const p of [pts[0], pts[3]]) { const s = m(new THREE.SphereGeometry(0.17, 20, 20)); s.position.copy(p); g.add(s) }
  } else {
    const shaft = m(new THREE.CylinderGeometry(0.1, 0.1, 0.85, 16)); shaft.rotation.z = -Math.PI / 2; shaft.position.x = -0.1
    const head = m(new THREE.ConeGeometry(0.26, 0.42, 24)); head.rotation.z = -Math.PI / 2; head.position.x = 0.52
    g.add(shaft, head)
  }
  return g
}

export function GateIcon3D({ shape, color, size = 42 }: { shape: GateShape; color: string; size?: number }) {
  const ref = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    const canvas = ref.current
    if (!canvas) return
    let renderer: THREE.WebGLRenderer
    try {
      renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true })
    } catch {
      return // no WebGL (test/jsdom or unsupported) — leave an empty canvas
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
    renderer.setSize(size, size, false)

    const scene = new THREE.Scene()
    const cam = new THREE.PerspectiveCamera(35, 1, 0.1, 10)
    cam.position.set(0, 0, 4)
    scene.add(new THREE.HemisphereLight(0xdfe7ea, 0x0e141a, 1.0))
    const key = new THREE.DirectionalLight(0xffffff, 1.6); key.position.set(2, 3, 4); scene.add(key)
    const rim = new THREE.DirectionalLight(0x9fd4cc, 0.5); rim.position.set(-3, -1, -2); scene.add(rim)

    const obj = buildShape(shape, color)
    obj.rotation.set(0.25, -0.5, 0) // a pleasing static 3/4 rest pose
    scene.add(obj)
    const draw = () => renderer.render(scene, cam)
    draw() // one static frame — no animation at rest

    // Spin only while the gate is hovered (idle icons cost nothing).
    const host = canvas.parentElement
    let raf = 0
    const tick = () => { obj.rotation.y += 0.02; draw(); raf = requestAnimationFrame(tick) }
    const enter = () => { if (!raf) tick() }
    const leave = () => { cancelAnimationFrame(raf); raf = 0 }
    host?.addEventListener('pointerenter', enter)
    host?.addEventListener('pointerleave', leave)

    return () => {
      cancelAnimationFrame(raf)
      host?.removeEventListener('pointerenter', enter)
      host?.removeEventListener('pointerleave', leave)
      obj.traverse((o) => {
        const mesh = o as THREE.Mesh
        mesh.geometry?.dispose?.()
        const mm = mesh.material as THREE.Material | undefined
        mm?.dispose?.()
      })
      renderer.dispose()
    }
  }, [shape, color, size])

  return <canvas ref={ref} className="gico" width={size} height={size} aria-hidden />
}
