import { useEffect, useRef } from 'react'
import * as THREE from 'three'
import { OBJLoader } from 'three/addons/loaders/OBJLoader.js'
import { Icon } from './Icons'

/** Renders the selected mesh on a dark device stage. Flat-shaded sage, matte, no glow. */
export function Viewport({ file, name }: { file: File | null; name: string }) {
  const hostRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const host = hostRef.current
    if (!host || !file) return

    let disposed = false
    let raf = 0
    const w = host.clientWidth || 600
    const h = host.clientHeight || 360

    const scene = new THREE.Scene()
    scene.background = new THREE.Color('#100F0A')
    const cam = new THREE.PerspectiveCamera(40, w / h, 0.01, 100)
    const renderer = new THREE.WebGLRenderer({ antialias: true })
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2))
    renderer.setSize(w, h)
    host.appendChild(renderer.domElement)

    scene.add(new THREE.HemisphereLight(0xcfcab8, 0x1a1912, 1.1))
    const key = new THREE.DirectionalLight(0xffffff, 0.55)
    key.position.set(2, 4, 3)
    scene.add(key)

    const material = new THREE.MeshStandardMaterial({ color: '#586040', roughness: 0.85, metalness: 0.08, flatShading: true })
    let root: THREE.Object3D | null = null

    file.text().then((txt) => {
      if (disposed) return
      try {
        const obj = new OBJLoader().parse(txt)
        obj.traverse((o: THREE.Object3D) => { const m = o as THREE.Mesh; if (m.isMesh) m.material = material })
        const box = new THREE.Box3().setFromObject(obj)
        const center = box.getCenter(new THREE.Vector3())
        const size = box.getSize(new THREE.Vector3())
        obj.position.sub(center)
        const r = Math.max(size.x, size.y, size.z) || 1
        cam.position.set(r * 1.5, r * 1.0, r * 2.2)
        cam.lookAt(0, 0, 0)
        root = obj
        scene.add(obj)
      } catch {
        /* non-OBJ or parse error — leave the empty stage */
      }
    })

    const onResize = () => {
      const nw = host.clientWidth, nh = host.clientHeight
      if (!nw || !nh) return
      cam.aspect = nw / nh; cam.updateProjectionMatrix(); renderer.setSize(nw, nh)
    }
    const ro = new ResizeObserver(onResize)
    ro.observe(host)

    const tick = () => { if (root) root.rotation.y += 0.004; renderer.render(scene, cam); raf = requestAnimationFrame(tick) }
    tick()

    return () => {
      disposed = true
      cancelAnimationFrame(raf)
      ro.disconnect()
      renderer.dispose()
      material.dispose()
      if (renderer.domElement.parentNode === host) host.removeChild(renderer.domElement)
    }
  }, [file])

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
