import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { TransformControls } from 'three/addons/controls/TransformControls.js'
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'
import { OBJLoader } from 'three/addons/loaders/OBJLoader.js'
import { Icon } from './Icons'
import { DragField } from './DragField'
import { MaskRail } from './MaskRail'
import { applyCategorical, applyScalar, buildMarkers, buildVectorSamples } from './maskRender'
import { computeMask, listMasks, maskProviders, type Mask, type MaskProviderMeta } from './masks'
import type { CapPlane, CapResult, PAP, Part, Verdict } from './api'

const SAGE = 0x34c0ad, FAIL = 0xe0694f, IDLE = 0x5e676e, AMBER = 0xd9a84c
const DEG = Math.PI / 180
// the world group is canonical Z-up but three renders Y-up (world.rotation.x = -90°),
// so convert between a three-space point and the canonical coords the UI shows.
const toCanon = (v: THREE.Vector3): number[] => [v.x, -v.z, v.y]
const toThree = (c: number[]): THREE.Vector3 => new THREE.Vector3(c[0] ?? 0, c[2] ?? 0, -(c[1] ?? 0))
const AXIS = ['#E0694F', '#6FBF73', '#5C8BD6']   // X red · Y green · Z blue
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
  model: THREE.Object3D | null   // the loaded model root (cap gizmo parents to this)
  capGizmo: THREE.Group | null   // the manual cap-plane gizmo (child of model, native frame)
  transform: TransformControls | null   // drag handles for the cap plane
  capContour: THREE.LineSegments | null // live outline where the plane cuts the mesh
  capCache: CapGeo[] | null      // per-mesh model-local positions for the contour
  capDirty: boolean              // contour needs recompute (plane moved / resized)
  capHalf: number                // current lid half-extent (native units)
  forceGroup: THREE.Group     // gravity-arrow field (reused by the gravity_field overlay)
  forceBuilt: boolean         // gravity field already raycast for current content (cache)
  gradMat: THREE.ShaderMaterial   // (legacy gradient material; kept for makeGradientMat)
  groups: Group[]             // material groups of the loaded model (unused by masks now)
  maskContent: THREE.Group    // convex-part representation masks render onto
  maskGroups: Group[]         // one group per convex part (name === part id)
  overlayGroup: THREE.Group   // marker / vector-sample overlays (canonical frame)
  radius: number              // content bounding radius (marker/axis scale)
  urls: string[]              // blob URLs to revoke
  footprint: THREE.LineLoop
  comDot: THREE.Mesh
  plumb: THREE.Line
  landing: THREE.Mesh
  human: THREE.Group          // 1.8 m human reference for scale comparison
  ruler: THREE.Group          // measure-tool markers + line (three world frame)
  showGiz: boolean            // corner orientation gizmo on/off
  swept: THREE.Mesh           // door swept-volume keep-clear wedge (WP-6)
  setCam: (v: 'recenter' | 'top' | 'front' | 'side' | 'persp') => void
  raf: number
}

// A simple ~1.8 m human reference (canonical Z-up, feet at z=0) for scale comparison.
// Cylinders default along local Y, so each is tilted +90° about X to stand along Z.
function buildHuman(): THREE.Group {
  const g = new THREE.Group()
  const mat = new THREE.MeshStandardMaterial({ color: 0x707a82, roughness: 0.7, metalness: 0.05, transparent: true, opacity: 0.82 })
  const stand = (geo: THREE.BufferGeometry, x: number, z: number) => {
    const m = new THREE.Mesh(geo, mat); m.position.set(x, 0, z); m.rotation.x = Math.PI / 2; g.add(m)
  }
  stand(new THREE.CylinderGeometry(0.07, 0.06, 0.9, 14), -0.1, 0.45)  // legs
  stand(new THREE.CylinderGeometry(0.07, 0.06, 0.9, 14), 0.1, 0.45)
  stand(new THREE.CylinderGeometry(0.17, 0.14, 0.62, 16), 0, 1.2)     // torso
  stand(new THREE.CylinderGeometry(0.05, 0.05, 0.6, 12), -0.24, 1.2)  // arms
  stand(new THREE.CylinderGeometry(0.05, 0.05, 0.6, 12), 0.24, 1.2)
  const head = new THREE.Mesh(new THREE.SphereGeometry(0.12, 20, 16), mat); head.position.set(0, 0, 1.64); g.add(head)
  g.visible = false
  return g
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

function clearGroup(g: THREE.Group) {
  while (g.children.length) {
    const c = g.children[0]
    g.remove(c)
    c.traverse?.((o) => {
      const m = o as THREE.Mesh
      m.geometry?.dispose?.()
      const mat = m.material as THREE.Material | THREE.Material[] | undefined
      Array.isArray(mat) ? mat.forEach((x) => x.dispose?.()) : mat?.dispose?.()
    })
  }
}

// Paint the active surface mask onto the part groups + (re)build the overlays. This is the
// single place the mask state becomes pixels (replaces the old textured/masks/inertia view).
function restoreOriginal(groups: Group[]) {
  for (const g of groups) g.meshes.forEach((m, i) => { if (g.orig[i]) m.material = g.orig[i] })
}

function applyMasks(r: Refs, surface: string, overlays: Set<string>, masks: Mask[]) {
  const surfaceMask = surface !== 'textured' ? masks.find((m) => m.id === surface) : undefined
  // Mask data is keyed by part id. If the bake produced convex parts WITH geometry we paint
  // those proxies (maskContent); otherwise the "parts" are the model's material groups
  // (e.g. a multi-material tree: branches/leaves/trunk) so we recolour the real model in place.
  const useParts = r.maskGroups.length > 0
  const groups = useParts ? r.maskGroups : r.groups
  r.maskContent.visible = useParts
  r.content.visible = !useParts

  if (!surfaceMask) {
    restoreOriginal(groups)
  } else if (surfaceMask.archetype === 'categorical') {
    applyCategorical(groups, surfaceMask.data.regions)
  } else if (surfaceMask.archetype === 'scalar') {
    applyScalar(groups, surfaceMask.data.per_part, surfaceMask.data.range, surfaceMask.data.ramp)
  } else {
    restoreOriginal(groups)
  }

  clearGroup(r.overlayGroup)
  let gravity = false
  for (const m of masks) {
    if (!overlays.has(m.id)) continue
    if (m.archetype === 'markers') r.overlayGroup.add(buildMarkers(m.data, r.radius || 0.3))
    else if (m.archetype === 'vector') {
      if (m.data.field === 'gravity') gravity = true
      else r.overlayGroup.add(buildVectorSamples(m.data))
    }
  }
  if (gravity) {
    // Build the field ONCE per content (raycasting a dense mesh is expensive); after that a
    // toggle is just a visibility flip — no main-thread freeze.
    if (!r.forceBuilt) {
      r.scene.updateMatrixWorld(true)
      const target = useParts ? r.maskContent : r.content
      const box = new THREE.Box3().setFromObject(target)
      if (!box.isEmpty()) { buildForceField(r.forceGroup, target, box); r.forceBuilt = true }
    }
    r.forceGroup.visible = true
  } else {
    r.forceGroup.visible = false
  }
}

function clearContent(r: Refs) {
  // NB: we deliberately do NOT revoke the texture/.bin blob URLs here — GLTFLoader
  // loads textures asynchronously, and revoking an in-flight blob (e.g. under React
  // StrictMode's double-invoke) makes every texture fail with ERR_FILE_NOT_FOUND.
  // The handful of blob URLs per load is a bounded leak the browser frees on unload.
  for (const g of r.groups) g.meshes.forEach((m) => (m.userData.maskMat as THREE.Material | undefined)?.dispose())
  for (const g of r.maskGroups) g.meshes.forEach((m) => (m.userData.maskMat as THREE.Material | undefined)?.dispose())
  r.groups = []
  r.maskGroups = []
  disposeCapGizmo(r)
  r.model = null
  for (const grp of [r.content, r.maskContent, r.overlayGroup, r.forceGroup]) {
    while (grp.children.length) {
      const c = grp.children[0]
      grp.remove(c)
      c.traverse?.((o) => { const m = o as THREE.Mesh; m.geometry?.dispose?.() })
    }
  }
  r.forceGroup.visible = false
  r.forceBuilt = false
}

// Tear down the whole cap tool: drag handles, plane gizmo, cut outline + vertex cache.
function disposeCapGizmo(r: Refs) {
  const free = (o: THREE.Object3D | null) => {
    if (!o) return
    o.parent?.remove(o)
    o.traverse((c) => {
      const m = c as THREE.Mesh
      m.geometry?.dispose?.()
      const mat = m.material as THREE.Material | THREE.Material[] | undefined
      if (Array.isArray(mat)) mat.forEach((x) => x.dispose?.())
      else mat?.dispose?.()
    })
  }
  if (r.transform) {
    try { r.transform.detach(); r.scene.remove(r.transform.getHelper()); r.transform.dispose() } catch { /* noop */ }
    r.transform = null
  }
  free(r.capGizmo); r.capGizmo = null
  free(r.capContour); r.capContour = null
  r.capCache = null
  r.controls.enabled = true
}

// Frame camera + floor grid to the content so any mesh scale reads right.
function frame(r: Refs) {
  r.scene.updateMatrixWorld(true)
  // box whichever representation has geometry (model in content, or part masks)
  const box = new THREE.Box3().setFromObject(r.content)
  if (box.isEmpty()) box.setFromObject(r.maskContent)
  if (box.isEmpty()) return
  const center = box.getCenter(new THREE.Vector3())
  const radius = Math.max(box.getBoundingSphere(new THREE.Sphere()).radius, 1e-3)
  r.radius = radius
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

// ---- manual cap-plane tool -------------------------------------------------
// The gizmo is parented to the loaded model so its LOCAL transform is already in the
// model's native coordinate frame — the same frame the bake loads the mesh in — so the
// plane the user lines up by eye maps straight to the backend with no axis juggling.
const CAP_TEAL = 0x34c0ad
const CAP_LINE = 0x6ff7e6   // bright cut-outline colour

type CapState = { sizeFrac: number; mode: 'translate' | 'rotate' }
// one cached mesh's geometry in the model's local (native) frame, for the cut contour
type CapGeo = { pos: Float32Array; index: ArrayLike<number> | null; tris: number; stride: number }

// The model's AABB expressed in the model's OWN local frame (native coords), so slider
// ranges and the gizmo sit in the same frame we send to the backend.
function modelLocalBox(model: THREE.Object3D): THREE.Box3 {
  model.updateMatrixWorld(true)
  const inv = new THREE.Matrix4().copy(model.matrixWorld).invert()
  const box = new THREE.Box3()
  const v = new THREE.Vector3()
  model.traverse((o) => {
    const m = o as THREE.Mesh
    if (!m.isMesh || !m.geometry) return
    const g = m.geometry as THREE.BufferGeometry
    if (!g.boundingBox) g.computeBoundingBox()
    const bb = g.boundingBox
    if (!bb) return
    for (const xi of [bb.min.x, bb.max.x]) for (const yi of [bb.min.y, bb.max.y]) for (const zi of [bb.min.z, bb.max.z]) {
      v.set(xi, yi, zi).applyMatrix4(m.matrixWorld).applyMatrix4(inv)
      box.expandByPoint(v)
    }
  })
  return box
}

// Build the gizmo: a translucent square lid + a crisp border. The TransformControls
// handles convey the axes/orientation, so no extra normal arrow. setLidSize sizes it.
function buildCapGizmo(): THREE.Group {
  const g = new THREE.Group()
  const lid = new THREE.Mesh(
    new THREE.PlaneGeometry(1, 1),
    new THREE.MeshBasicMaterial({ color: CAP_TEAL, transparent: true, opacity: 0.2, side: THREE.DoubleSide, depthWrite: false }),
  )
  lid.name = 'lid'
  g.add(lid)
  const border = new THREE.LineSegments(
    new THREE.EdgesGeometry(new THREE.PlaneGeometry(1, 1)),
    new THREE.LineBasicMaterial({ color: CAP_TEAL, transparent: true, opacity: 0.9, depthTest: false }),
  )
  border.name = 'border'
  border.renderOrder = 999
  g.add(border)
  g.renderOrder = 998
  return g
}

// Lid half-extent in native units for a given size fraction (orientation-independent,
// so it works after the plane is freely rotated). Based on the model's overall size.
function capHalfFor(box: THREE.Box3, sizeFrac: number): number {
  const s = box.getSize(new THREE.Vector3())
  const maxDim = Math.max(s.x, s.y, s.z, 1e-4)
  return Math.max(sizeFrac * maxDim * 0.6, 1e-4)
}

// Initial placement: sit the lid near the base of the model's tallest axis, facing along
// it. From here the user drags/rotates it freely with the TransformControls handles.
function initCapGizmo(g: THREE.Group, box: THREE.Box3) {
  const s = box.getSize(new THREE.Vector3())
  const idx = s.x >= s.y && s.x >= s.z ? 0 : s.y >= s.z ? 1 : 2
  const origin = box.getCenter(new THREE.Vector3())
  origin.setComponent(idx, box.min.getComponent(idx) + 0.08 * s.getComponent(idx))
  const normal = new THREE.Vector3().setComponent(idx, 1)
  g.position.copy(origin)
  g.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), normal)
}

// Scale the lid quad / border / normal-arrow to the current half-extent.
function setLidSize(g: THREE.Group, half: number) {
  ;(g.getObjectByName('lid') as THREE.Mesh | undefined)?.scale.set(half * 2, half * 2, 1)
  ;(g.getObjectByName('border') as THREE.LineSegments | undefined)?.scale.set(half * 2, half * 2, 1)
  const arrow = g.getObjectByName('arrow') as THREE.ArrowHelper | undefined
  if (arrow) { const len = half * 0.9; arrow.setLength(len, len * 0.32, len * 0.2) }
}

// The plane's origin (model-local) + unit normal (the gizmo's local +Z), read live from
// the gizmo's current transform — this is what we send to the backend and use for the cut.
function capPlaneOf(g: THREE.Group): { origin: THREE.Vector3; normal: THREE.Vector3 } {
  return {
    origin: g.position.clone(),
    normal: new THREE.Vector3(0, 0, 1).applyQuaternion(g.quaternion).normalize(),
  }
}

// Cache every mesh's vertices in the model's local (native) frame once, so the live cut
// contour only has to run the cheap plane/triangle test on drag — not re-transform verts.
function buildCapCache(model: THREE.Object3D): CapGeo[] {
  model.updateMatrixWorld(true)
  const inv = new THREE.Matrix4().copy(model.matrixWorld).invert()
  const out: CapGeo[] = []
  const v = new THREE.Vector3()
  const mat = new THREE.Matrix4()
  model.traverse((o) => {
    const m = o as THREE.Mesh
    if (!m.isMesh || !m.geometry) return
    const geo = m.geometry as THREE.BufferGeometry
    const posAttr = geo.getAttribute('position') as THREE.BufferAttribute | undefined
    if (!posAttr) return
    mat.multiplyMatrices(inv, m.matrixWorld)
    const n = posAttr.count
    const pos = new Float32Array(n * 3)
    for (let i = 0; i < n; i++) {
      v.fromBufferAttribute(posAttr, i).applyMatrix4(mat)
      pos[i * 3] = v.x; pos[i * 3 + 1] = v.y; pos[i * 3 + 2] = v.z
    }
    const index = geo.index ? (geo.index.array as ArrayLike<number>) : null
    const tris = index ? index.length / 3 : n / 3
    // keep the per-frame work bounded on huge foliage meshes by sampling triangles
    const stride = Math.max(1, Math.ceil(tris / 180_000))
    out.push({ pos, index, tris, stride })
  })
  return out
}

// Recompute the cut outline: the segments where the current plane crosses the mesh,
// clipped to the lid rectangle (so it shows exactly the opening the cap will cover).
function recomputeContour(r: Refs) {
  const g = r.capGizmo, cache = r.capCache, line = r.capContour
  if (!g || !cache || !line) return
  const { origin, normal } = capPlaneOf(g)
  const seed = Math.abs(normal.x) < 0.9 ? new THREE.Vector3(1, 0, 0) : new THREE.Vector3(0, 1, 0)
  const u = new THREE.Vector3().crossVectors(normal, seed).normalize()
  const w = new THREE.Vector3().crossVectors(normal, u)
  const ox = origin.x, oy = origin.y, oz = origin.z, nx = normal.x, ny = normal.y, nz = normal.z
  const ux = u.x, uy = u.y, uz = u.z, wx = w.x, wy = w.y, wz = w.z
  const half = r.capHalf
  const segs: number[] = []
  const MAX = 24_000 * 6
  const P = [0, 0, 0, 0, 0, 0]
  for (const cg of cache) {
    const pos = cg.pos, index = cg.index, stride = cg.stride, tris = cg.tris
    for (let t = 0; t < tris && segs.length < MAX; t += stride) {
      const ia = index ? index[t * 3] : t * 3
      const ib = index ? index[t * 3 + 1] : t * 3 + 1
      const ic = index ? index[t * 3 + 2] : t * 3 + 2
      const ax = pos[ia * 3], ay = pos[ia * 3 + 1], az = pos[ia * 3 + 2]
      const bx = pos[ib * 3], by = pos[ib * 3 + 1], bz = pos[ib * 3 + 2]
      const cx = pos[ic * 3], cy = pos[ic * 3 + 1], cz = pos[ic * 3 + 2]
      const da = (ax - ox) * nx + (ay - oy) * ny + (az - oz) * nz
      const db = (bx - ox) * nx + (by - oy) * ny + (bz - oz) * nz
      const dc = (cx - ox) * nx + (cy - oy) * ny + (cz - oz) * nz
      if ((da > 0 && db > 0 && dc > 0) || (da < 0 && db < 0 && dc < 0)) continue
      let k = 0
      if ((da < 0) !== (db < 0)) { const tt = da / (da - db); P[0] = ax + (bx - ax) * tt; P[1] = ay + (by - ay) * tt; P[2] = az + (bz - az) * tt; k = 1 }
      if ((db < 0) !== (dc < 0)) { const tt = db / (db - dc); const j = k * 3; P[j] = bx + (cx - bx) * tt; P[j + 1] = by + (cy - by) * tt; P[j + 2] = bz + (cz - bz) * tt; k++ }
      if (k < 2 && (dc < 0) !== (da < 0)) { const tt = dc / (dc - da); const j = k * 3; P[j] = cx + (ax - cx) * tt; P[j + 1] = cy + (ay - cy) * tt; P[j + 2] = cz + (az - cz) * tt; k++ }
      if (k < 2) continue
      const mx = (P[0] + P[3]) / 2 - ox, my = (P[1] + P[4]) / 2 - oy, mz = (P[2] + P[5]) / 2 - oz
      if (Math.abs(mx * ux + my * uy + mz * uz) > half || Math.abs(mx * wx + my * wy + mz * wz) > half) continue
      segs.push(P[0], P[1], P[2], P[3], P[4], P[5])
    }
  }
  const arr = new Float32Array(segs)
  line.geometry.setAttribute('position', new THREE.BufferAttribute(arr, 3))
  line.geometry.setDrawRange(0, arr.length / 3)
  line.geometry.computeBoundingSphere()
}

// A vertical gradient material (cool teal at the top → warm amber at the base) keyed
// to world height — the "force gradient" mask shown in the inertia view. Lit by a
// fixed direction so the model's shape still reads.
function makeGradientMat(): THREE.ShaderMaterial {
  return new THREE.ShaderMaterial({
    uniforms: { uMin: { value: 0 }, uMax: { value: 1 }, cBot: { value: new THREE.Color(0xd9a84c) }, cTop: { value: new THREE.Color(0x34c0ad) } },
    vertexShader: `varying float vY; varying vec3 vN;
      void main(){ vec4 wp = modelMatrix*vec4(position,1.0); vY = wp.y; vN = normalize(normalMatrix*normal);
      gl_Position = projectionMatrix*modelViewMatrix*vec4(position,1.0); }`,
    fragmentShader: `uniform float uMin; uniform float uMax; uniform vec3 cBot; uniform vec3 cTop; varying float vY; varying vec3 vN;
      void main(){ float t = clamp((vY-uMin)/max(uMax-uMin,1e-4),0.0,1.0); vec3 base = mix(cBot,cTop,t);
      float d = 0.5 + 0.5*dot(vN, normalize(vec3(0.35,0.8,0.45))); gl_FragColor = vec4(base*(0.5+0.5*d),1.0); }`,
    side: THREE.DoubleSide,
  })
}

// One subtle, translucent gravity vector: it STARTS at the surface point and
// points a short way straight down (muted amber).
function gravityArrow(surfaceY: number, x: number, z: number, length: number, radius: number): THREE.Group {
  const g = new THREE.Group()
  const mat = new THREE.MeshBasicMaterial({ color: 0xd9a84c, transparent: true, opacity: 0.28, depthWrite: false })
  const sl = length * 0.72
  const shaft = new THREE.Mesh(new THREE.CylinderGeometry(radius * 0.34, radius * 0.34, sl, 6), mat)
  shaft.position.set(x, surfaceY - sl / 2, z); g.add(shaft)            // tail at the surface, going down
  const head = new THREE.Mesh(new THREE.ConeGeometry(radius, length * 0.28, 10), mat)
  head.rotation.x = Math.PI; head.position.set(x, surfaceY - sl - length * 0.14, z); g.add(head)
  return g
}

// A field of downward gravity arrows, each raycast straight down and SNAPPED so its
// tip rests on the lowest surface of the model at that (x,z) — i.e. on the contact
// point gravity drives the body toward. Skips columns where the model is hollow.
function buildForceField(group: THREE.Group, content: THREE.Object3D, box: THREE.Box3) {
  while (group.children.length) { const c = group.children[0]; group.remove(c); c.traverse?.((o) => { const m = o as THREE.Mesh; m.geometry?.dispose?.() }) }
  if (box.isEmpty()) return
  const size = box.getSize(new THREE.Vector3())
  const R = Math.max(size.x, size.y, size.z, 1e-3)
  const rad = R * 0.011
  const len = size.y * 0.09 + R * 0.03
  const ray = new THREE.Raycaster()
  const down = new THREE.Vector3(0, -1, 0)
  const N = 4
  for (let ix = 0; ix < N; ix++) for (let iz = 0; iz < N; iz++) {
    const x = box.min.x + (0.16 + (ix / (N - 1)) * 0.68) * size.x
    const z = box.min.z + (0.16 + (iz / (N - 1)) * 0.68) * size.z
    ray.set(new THREE.Vector3(x, box.max.y + R, z), down)
    const hits = ray.intersectObject(content, true)
    if (!hits.length) continue
    group.add(gravityArrow(hits[hits.length - 1].point.y, x, z, len, rad)) // lowest hit
  }
}

/** Dark device stage: renders the real textured model (materials/textures intact),
 *  with an extensible mask rail (surface masks recolour, overlays stack). Plus the verdict
 *  viz (CoM, plumb, support footprint). Canonical is Z-up; world tilted so Z reads up. */
export function Viewport({ name, file, extras, pap, pos, rot = [0, 0, 0], scale = 1, verdict, status, swept, onDropFiles, capping, onApplyCap, onExitCap, busy, capResult, onCapAgain, onDismissCap }: {
  name: string; file?: File | null; extras?: File[]
  pap: PAP | null; pos: number[]; rot?: number[]; scale?: number; verdict: Verdict | null
  status?: 'queued' | 'converting' | 'baking' | 'ok' | 'error' | 'declared'
  swept?: { vertices: number[][]; faces: number[][] } | null
  onDropFiles?: (files: File[]) => void
  capping?: boolean                       // the manual cap-plane tool is active
  onApplyCap?: (plane: CapPlane) => void  // re-bake the mesh with the placed cap plane
  onExitCap?: () => void                  // leave the cap tool without applying
  busy?: boolean                          // a bake is in flight
  capResult?: CapResult | null            // outcome of the last cap (success card)
  onCapAgain?: () => void                 // reopen the cap tool to seal another opening
  onDismissCap?: () => void               // dismiss the result card
}) {
  const hostRef = useRef<HTMLDivElement>(null)
  const refs = useRef<Refs | null>(null)
  const posRef = useRef(pos); posRef.current = pos
  // mask system state
  const [catalog, setCatalog] = useState<MaskProviderMeta[]>([])
  const [masks, setMasks] = useState<Mask[]>([])
  const [surface, setSurface] = useState('textured')
  const [overlays, setOverlays] = useState<Set<string>>(() => new Set())
  const [computing, setComputing] = useState<Set<string>>(() => new Set())
  const [maskErrors, setMaskErrors] = useState<Record<string, string>>({})
  const assetId = pap?.asset_id ?? null
  const [hasContent, setHasContent] = useState(false)
  const [dropping, setDropping] = useState(false)
  const [camView, setCamView] = useState<'top' | 'front' | 'side' | 'persp'>('persp')
  // manual cap-plane tool state (lid size fraction + drag/rotate handle mode)
  const [cap, setCap] = useState<CapState>({ sizeFrac: 0.5, mode: 'translate' })
  const capBox = useRef<THREE.Box3 | null>(null)
  // viewport view options + measure tool
  const [showGiz, setShowGiz] = useState(true)
  const [showGrid, setShowGrid] = useState(true)
  const [showHuman, setShowHuman] = useState(false)
  const [viewMenu, setViewMenu] = useState(false)
  const [rulerOn, setRulerOn] = useState(false)
  const [rp, setRp] = useState<number[][]>([])     // measure points, canonical Z-up coords
  const [rSel, setRSel] = useState(-1)             // which point's gizmo is active
  const rMarkers = useRef<THREE.Mesh[]>([])
  const rLine = useRef<THREE.Line | null>(null)
  const rulerTC = useRef<TransformControls | null>(null)
  const rDragging = useRef(false)
  const rSelRef = useRef(rSel); rSelRef.current = rSel

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
    const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true })
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
    const maskContent = new THREE.Group(); maskContent.visible = false; meshHolder.add(maskContent)
    const overlayGroup = new THREE.Group(); meshHolder.add(overlayGroup)
    const forceGroup = new THREE.Group(); forceGroup.visible = false; scene.add(forceGroup)
    const gradMat = makeGradientMat()

    const footprint = new THREE.LineLoop(new THREE.BufferGeometry(), new THREE.LineBasicMaterial({ color: IDLE }))
    world.add(footprint)
    const comDot = new THREE.Mesh(new THREE.SphereGeometry(0.02, 16, 16), new THREE.MeshBasicMaterial({ color: AMBER }))
    comDot.visible = false; world.add(comDot)
    const plumb = new THREE.Line(new THREE.BufferGeometry(), new THREE.LineDashedMaterial({ color: IDLE, dashSize: 0.03, gapSize: 0.02 }))
    plumb.visible = false; world.add(plumb)
    const landing = new THREE.Mesh(new THREE.RingGeometry(0.012, 0.022, 20), new THREE.MeshBasicMaterial({ color: IDLE, side: THREE.DoubleSide }))
    landing.rotation.x = -Math.PI / 2; landing.visible = false; world.add(landing)
    const human = buildHuman(); world.add(human)
    const ruler = new THREE.Group(); scene.add(ruler)   // measure markers live in three world coords
    // door swept-volume wedge (WP-6): translucent amber keep-clear solid at origin
    // (named sweptMesh so it never shadows the `swept` prop inside this setup scope)
    const sweptMesh = new THREE.Mesh(
      new THREE.BufferGeometry(),
      new THREE.MeshBasicMaterial({ color: AMBER, transparent: true, opacity: 0.22, side: THREE.DoubleSide, depthWrite: false }),
    )
    sweptMesh.visible = false; world.add(sweptMesh)

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
      if (r.capDirty) { recomputeContour(r); r.capDirty = false }   // refresh the cut outline
      renderer.render(scene, cam)
      // overlay the axis gizmo in the bottom-left corner (toggleable)
      if (r.showGiz) {
        _dir.copy(cam.position).sub(controls.target).normalize().multiplyScalar(4)
        gcam.position.copy(_dir); gcam.up.copy(cam.up); gcam.lookAt(0, 0, 0)
        renderer.getSize(_sz)
        renderer.autoClear = false
        renderer.clearDepth()
        renderer.setViewport(12, 12, 78, 78)
        renderer.render(giz, gcam)
        renderer.setViewport(0, 0, _sz.x, _sz.y)
        renderer.autoClear = true
      }
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

    const r: Refs = { host, renderer, scene, cam, controls, grid, meshHolder, content, model: null, capGizmo: null, transform: null, capContour: null, capCache: null, capDirty: false, capHalf: 0, forceGroup, forceBuilt: false, gradMat, groups: [], maskContent, maskGroups: [], overlayGroup, radius: 0.3, urls: [], footprint, comDot, plumb, landing, human, ruler, showGiz: true, swept: sweptMesh, setCam, raf: 0 }
    refs.current = r
    tick()
    return () => {
      cancelAnimationFrame(r.raf); ro.disconnect(); controls.dispose(); clearContent(r); renderer.dispose()
      if (renderer.domElement.parentNode === host) host.removeChild(renderer.domElement)
      refs.current = null
    }
  }, [])

  // ---- load content (real model if we have the file, else convex-part masks) ----
  // stable signature of the sidecars so a re-rendered (but unchanged) extras array
  // doesn't retrigger a full reload + reframe flicker.
  const extrasKey = (extras ?? []).map((f) => f.name).join('|')
  useEffect(() => {
    const r = refs.current
    if (!r) return
    let cancelled = false
    const p = posRef.current
    r.meshHolder.position.set(p[0] ?? 0, p[1] ?? 0, p[2] ?? 0)
    clearContent(r)
    setHasContent(false)
    r.forceGroup.visible = false
    // part data (centroids/verts) is in the bake's raw frame; the loaded model gets an
    // upright rotation. Reset the overlay/proxy frame, then re-sync it to the model below
    // so markers/proxies line up with the visible mesh.
    for (const g of [r.maskContent, r.overlayGroup]) { g.position.set(0, 0, 0); g.quaternion.identity(); g.scale.set(1, 1, 1) }

    // convex-part representation masks paint onto — always built when parts exist.
    const buildMaskGeom = () => {
      if (pap?.parts?.some((pt) => pt.verts?.length)) r.maskGroups = buildPartGroup(r.maskContent, pap.parts)
    }

    if (file) {
      loadModel(file, extras ?? [], r.urls).then((model) => {
        if (cancelled || refs.current !== r) return
        r.content.add(model)
        r.model = model
        // line the overlays + convex proxies up with the model's upright transform
        for (const g of [r.maskContent, r.overlayGroup]) {
          g.position.copy(model.position); g.quaternion.copy(model.quaternion); g.scale.copy(model.scale)
        }
        r.groups = buildGroups(model)
        buildMaskGeom()
        frame(r)
        applyMasks(r, 'textured', new Set(), [])
        setHasContent(true)
      }).catch((e) => { if (!cancelled) console.error('model load failed', e) })
    } else if (pap?.parts?.some((pt) => pt.verts?.length)) {
      buildMaskGeom()
      frame(r)
      r.human.position.set(-(r.radius + 0.45), 0, 0)   // park the human ref beside the freshly-sized model
      applyMasks(r, 'textured', new Set(), [])
      setHasContent(true)
    }
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [file, extrasKey, pap?.asset_id])

  // ---- fetch the provider catalog once ----
  useEffect(() => { maskProviders().then(setCatalog).catch(() => {}) }, [])

  // ---- on asset change: reset mask state + load any stored masks ----
  useEffect(() => {
    setSurface('textured'); setOverlays(new Set()); setMaskErrors({}); setMasks([])
    setRp([]); setRSel(-1)   // clear measure points so they don't leak across assets
    setCap({ sizeFrac: 0.5, mode: 'translate' })   // reset the cap tool to defaults
    if (!assetId) return
    let cancelled = false
    listMasks(assetId).then((ms) => { if (!cancelled) setMasks(ms) }).catch(() => {})
    return () => { cancelled = true }
  }, [assetId])

  // ---- paint the active surface mask + overlays whenever state changes ----
  useEffect(() => {
    const r = refs.current
    if (!r) return
    applyMasks(r, surface, overlays, masks)
  }, [surface, overlays, masks, hasContent])

  // ---- placement + verdict viz ----
  useEffect(() => {
    const r = refs.current
    if (!r || !pap) return
    const com = canonCom(pap.physical.com, name)
    // footprint half-extents: canonical horizontal axes (X, Y). glTF/glb are Y-up, so
    // the horizontal pair is native X and Z (native Y is the height).
    const obb = pap.geometry.obb, yup = /\.(gltf|glb)$/i.test(name)
    const s = scale || 1
    const hx = (obb?.[0] ?? 0.2) * s, hy = ((yup ? obb?.[2] : obb?.[1]) ?? 0.2) * s
    // placement rotation (euler° → radians, canonical XYZ) — drives the assembly and,
    // to match the world-anchored stability gate, orients the CoM and support footprint.
    const e = new THREE.Euler((rot[0] ?? 0) * DEG, (rot[1] ?? 0) * DEG, (rot[2] ?? 0) * DEG, 'XYZ')
    r.meshHolder.position.set(pos[0], pos[1], pos[2])
    r.meshHolder.rotation.copy(e)
    r.meshHolder.scale.setScalar(s)   // uniform placement scale (transform: scale → rotate → translate)
    // CoM gets the full transform (scale, rotate about origin, then translate by pos)…
    const comV = new THREE.Vector3(com[0] * s, com[1] * s, com[2] * s).applyEuler(e)
    const wx = pos[0] + comV.x, wy = pos[1] + comV.y, wz = pos[2] + comV.z
    // …while the support footprint is world-anchored: rotation orients it, translation does not.
    r.footprint.geometry.setFromPoints([
      new THREE.Vector3(-hx, -hy, 0), new THREE.Vector3(hx, -hy, 0),
      new THREE.Vector3(hx, hy, 0), new THREE.Vector3(-hx, hy, 0),
    ].map((c) => c.applyEuler(e)))
    r.comDot.position.set(wx, wy, wz); r.comDot.visible = true
    r.plumb.geometry.setFromPoints([new THREE.Vector3(wx, wy, wz), new THREE.Vector3(wx, wy, 0)])
    ;(r.plumb as THREE.Line).computeLineDistances(); r.plumb.visible = true
    r.landing.position.set(wx, wy, 0.001); r.landing.visible = true
    const stab = verdict?.gates.find((g) => g.gate === 'stability')
    const col = stab ? (stab.ok === false ? FAIL : stab.ok === true ? SAGE : IDLE) : IDLE
    ;(r.footprint.material as THREE.LineBasicMaterial).color.setHex(col)
    ;(r.plumb.material as THREE.LineDashedMaterial).color.setHex(col)
    ;(r.landing.material as THREE.MeshBasicMaterial).color.setHex(col)
  }, [pos, rot, scale, verdict, pap])

  // ---- view options: gizmo / grid / human reference toggles ----
  useEffect(() => {
    const r = refs.current
    if (!r) return
    r.showGiz = showGiz
    r.grid.visible = showGrid
    r.human.visible = showHuman
    // park the human just outside the content footprint so the two stand side by side
    r.human.position.set(-(r.radius + 0.45), 0, 0)
  }, [showGiz, showGrid, showHuman, hasContent, scale])

  // ---- measure tool: click to place P1/P2 (snap to the mesh in the way), click a
  //      point to select it. Each point then carries a drag gizmo + editable coords. ----
  useEffect(() => {
    const r = refs.current
    if (!r || !rulerOn) return
    const canvas = r.renderer.domElement
    const ray = new THREE.Raycaster()
    const ndc = new THREE.Vector2()
    let downX = 0, downY = 0, moved = false
    const onDown = (e: PointerEvent) => { downX = e.clientX; downY = e.clientY; moved = false }
    const onMove = (e: PointerEvent) => { if (Math.abs(e.clientX - downX) + Math.abs(e.clientY - downY) > 4) moved = true }
    const onUp = (e: PointerEvent) => {
      if (moved || rDragging.current) return   // orbit drag or gizmo drag, not a placement click
      const rect = canvas.getBoundingClientRect()
      ndc.set(((e.clientX - rect.left) / rect.width) * 2 - 1, -((e.clientY - rect.top) / rect.height) * 2 + 1)
      ray.setFromCamera(ndc, r.cam)
      // clicking an existing point selects it (so its gizmo + coord row light up)
      const onPts = ray.intersectObjects(rMarkers.current, false)
      if (onPts.length) {
        const idx = rMarkers.current.indexOf(onPts[0].object as THREE.Mesh)
        if (idx >= 0) setRSel(idx)
        return
      }
      // otherwise snap to the mesh in the way (or fall back to the ground plane)
      const targets: THREE.Object3D[] = []
      r.content.traverse((o) => { if ((o as THREE.Mesh).isMesh) targets.push(o) })
      r.maskContent.traverse((o) => { if ((o as THREE.Mesh).isMesh) targets.push(o) })
      const hits = ray.intersectObjects(targets, true)
      let pt: THREE.Vector3 | null = null
      if (hits.length) pt = hits[0].point.clone()
      else if (Math.abs(ray.ray.direction.y) > 1e-6) {
        const t = -r.cam.position.y / ray.ray.direction.y
        if (t > 0) pt = r.cam.position.clone().addScaledVector(ray.ray.direction, t)
      }
      if (!pt) return
      const c = toCanon(pt)
      setRp((prev) => {
        if (prev.length >= 2) { setRSel(0); return [c] }   // a third click starts fresh
        setRSel(prev.length)
        return [...prev, c]
      })
    }
    canvas.addEventListener('pointerdown', onDown)
    canvas.addEventListener('pointermove', onMove)
    canvas.addEventListener('pointerup', onUp)
    return () => {
      canvas.removeEventListener('pointerdown', onDown)
      canvas.removeEventListener('pointermove', onMove)
      canvas.removeEventListener('pointerup', onUp)
    }
  }, [rulerOn])

  // ---- measure tool: sync the 3D markers / line / drag gizmo to the points ----
  useEffect(() => {
    const r = refs.current
    if (!r) return
    const detachTC = () => {
      if (rulerTC.current) {
        try { rulerTC.current.detach(); r.scene.remove(rulerTC.current.getHelper()); rulerTC.current.dispose() } catch { /* noop */ }
        rulerTC.current = null
      }
    }
    if (!rulerOn) { detachTC(); clearGroup(r.ruler); rMarkers.current = []; rLine.current = null; return }
    if (rDragging.current) return   // never rebuild mid-drag

    // rebuild the marker spheres when the point count changes
    if (rMarkers.current.length !== rp.length) {
      detachTC(); clearGroup(r.ruler); rMarkers.current = []; rLine.current = null
      const rad = Math.max(0.014, r.radius * 0.028)
      rp.forEach(() => {
        const dot = new THREE.Mesh(new THREE.SphereGeometry(rad, 16, 14), new THREE.MeshBasicMaterial({ color: SAGE }))
        r.ruler.add(dot); rMarkers.current.push(dot)
      })
    }
    // position + highlight markers (canonical → three)
    rp.forEach((c, i) => {
      const m = rMarkers.current[i]; if (!m) return
      m.position.copy(toThree(c))
      ;(m.material as THREE.MeshBasicMaterial).color.setHex(i === rSel ? 0xffffff : SAGE)
      m.scale.setScalar(i === rSel ? 1.4 : 1)
    })
    // line between the two points
    if (rp.length === 2) {
      const pts = [toThree(rp[0]), toThree(rp[1])]
      if (!rLine.current) {
        rLine.current = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({ color: SAGE }))
        r.ruler.add(rLine.current)
      } else rLine.current.geometry.setFromPoints(pts)
    } else if (rLine.current) { r.ruler.remove(rLine.current); rLine.current.geometry.dispose(); rLine.current = null }

    // attach the drag gizmo to the selected point
    const target = rSel >= 0 ? rMarkers.current[rSel] : null
    if (target) {
      if (!rulerTC.current) {
        const tc = new TransformControls(r.cam, r.renderer.domElement)
        tc.setMode('translate'); tc.setSpace('world'); tc.setSize(0.7)
        r.scene.add(tc.getHelper())
        tc.addEventListener('dragging-changed', (ev) => {
          const dragging = !!ev.value
          rDragging.current = dragging
          r.controls.enabled = !dragging
          if (!dragging) {   // commit the dragged position back to canonical state
            const idx = rSelRef.current, m = rMarkers.current[idx]
            if (m) setRp((prev) => prev.map((c, i) => (i === idx ? toCanon(m.position) : c)))
          }
        })
        tc.addEventListener('objectChange', () => {   // live-update the line while dragging
          if (rMarkers.current.length === 2 && rLine.current) {
            rLine.current.geometry.setFromPoints([rMarkers.current[0].position, rMarkers.current[1].position])
          }
        })
        rulerTC.current = tc
      }
      rulerTC.current.attach(target)
    } else detachTC()
  }, [rulerOn, rp, rSel, hasContent])

  // ---- manual cap tool: build the draggable gizmo + live cut outline (or tear down) ----
  useEffect(() => {
    const r = refs.current
    if (!r) return
    if (capping && r.model && hasContent) {
      disposeCapGizmo(r)
      const box = modelLocalBox(r.model)
      capBox.current = box
      r.capHalf = capHalfFor(box, cap.sizeFrac)

      // the plane gizmo + the cut-outline line both live in the model's local frame
      const g = buildCapGizmo()
      initCapGizmo(g, box)
      setLidSize(g, r.capHalf)
      r.model.add(g); r.capGizmo = g

      const contour = new THREE.LineSegments(
        new THREE.BufferGeometry(),
        new THREE.LineBasicMaterial({ color: CAP_LINE, transparent: true, opacity: 0.95, depthTest: false }),
      )
      contour.renderOrder = 1001
      r.model.add(contour); r.capContour = contour
      r.capCache = buildCapCache(r.model)

      // TransformControls: real drag handles. Move by default; the window flips to rotate.
      const tc = new TransformControls(r.cam, r.renderer.domElement)
      tc.setSpace('local'); tc.setMode('translate'); tc.setSize(0.82)
      tc.attach(g)
      r.scene.add(tc.getHelper())
      tc.addEventListener('dragging-changed', (e) => { r.controls.enabled = !e.value })
      tc.addEventListener('objectChange', () => { r.capDirty = true })
      r.transform = tc
      r.controls.autoRotate = false
      r.capDirty = true
    } else {
      disposeCapGizmo(r)
      capBox.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [capping, hasContent])

  // ---- manual cap tool: resize the lid / switch handle mode from the window ----
  useEffect(() => {
    const r = refs.current
    if (!r || !r.capGizmo || !capBox.current || !capping) return
    r.capHalf = capHalfFor(capBox.current, cap.sizeFrac)
    setLidSize(r.capGizmo, r.capHalf)
    r.transform?.setMode(cap.mode)
    r.capDirty = true
  }, [cap, capping])

  const applyCap = () => {
    const r = refs.current, box = capBox.current
    if (!r || !r.capGizmo || !box || !onApplyCap) return
    const { origin, normal } = capPlaneOf(r.capGizmo)
    const half = r.capHalf
    const size = box.getSize(new THREE.Vector3())
    const maxDim = Math.max(size.x, size.y, size.z, 1e-4)
    const depth = Math.max(half * 0.5, maxDim * 0.03)
    onApplyCap({ origin: [origin.x, origin.y, origin.z], normal: [normal.x, normal.y, normal.z], half, depth })
  }

  // grab the live canvas as a PNG (for image-based HF/Gemini mask providers).
  const captureViewport = (): Promise<Blob | null> =>
    new Promise((res) => {
      const c = refs.current?.renderer.domElement
      if (!c) return res(null)
      c.toBlob((b) => res(b), 'image/png')
    })

  // compute a provider's mask on demand (auto-compute on click), storing the result.
  const runCompute = async (key: string) => {
    if (!assetId) return
    const prov = catalog.find((p) => p.key === key)
    if (!prov) return
    setComputing((s) => new Set(s).add(key))
    setMaskErrors((e) => { const n = { ...e }; delete n[key]; return n })
    try {
      let images: Blob[] = []
      if (prov.needs_images) { const b = await captureViewport(); if (b) images = [b] }
      // Vultr text-prompted mask: ask what to segment ("handle", "fragile glass", …).
      let params: Record<string, string> = {}
      if (key === 'text_mask') {
        const prompt = window.prompt('Segment what? (e.g. "handle", "fragile glass")')?.trim()
        if (!prompt) { setComputing((s) => { const n = new Set(s); n.delete(key); return n }); return }
        params = { prompt }
      }
      const m = await computeMask(assetId, key, images, params)
      setMasks((prev) => [...prev.filter((x) => x.id !== m.id), m])
    } catch {
      setMaskErrors((e) => ({ ...e, [key]: 'failed' }))
    } finally {
      setComputing((s) => { const n = new Set(s); n.delete(key); return n })
    }
  }

  const onSurface = (key: string) => {
    if (key !== 'textured' && !masks.some((m) => m.id === key) && !computing.has(key)) void runCompute(key)
    setSurface(key)
  }
  const onOverlay = (key: string) => {
    if (overlays.has(key)) { setOverlays((s) => { const n = new Set(s); n.delete(key); return n }); return }
    if (!masks.some((m) => m.id === key) && !computing.has(key)) void runCompute(key)
    setOverlays((s) => new Set(s).add(key))
  }

  // ---- door swept-volume wedge (WP-6) ----
  useEffect(() => {
    const r = refs.current
    if (!r) return
    const m = r.swept
    if (!swept || !swept.vertices.length || !swept.faces.length) { m.visible = false; return }
    const pos3 = new Float32Array(swept.vertices.length * 3)
    swept.vertices.forEach((v, i) => { pos3[i * 3] = v[0]; pos3[i * 3 + 1] = v[1]; pos3[i * 3 + 2] = v[2] })
    const idx: number[] = []
    for (const f of swept.faces) idx.push(f[0], f[1], f[2])
    const g = m.geometry
    g.setAttribute('position', new THREE.BufferAttribute(pos3, 3))
    g.setIndex(idx)
    g.computeVertexNormals()
    g.computeBoundingSphere()
    m.visible = true
  }, [swept])

  return (
    <section className="pane viewport">
      <header>
        <div className="t"><Icon name="aperture" /><span>Viewport{name ? ` · ${name}` : ''}</span></div>
      </header>
      <div className="vp-body">
      <div
        className={`stage${dropping ? ' dropping' : ''}`}
        onDragOver={onDropFiles ? (e) => {
          // only react to genuine file drags — not the browser's native
          // selection/element drag that an orbit click-drag can kick off
          if (!Array.from(e.dataTransfer.types).includes('Files')) return
          e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; if (!dropping) setDropping(true)
        } : undefined}
        onDragLeave={onDropFiles ? (e) => { if (e.currentTarget === e.target) setDropping(false) } : undefined}
        onDrop={onDropFiles ? (e) => {
          e.preventDefault(); setDropping(false)
          const files = Array.from(e.dataTransfer.files)
          if (files.length) onDropFiles(files)
        } : undefined}
      >
        <div className="cambar">
          <button className="cb-recenter" data-tip="Recenter" onClick={() => refs.current?.setCam('recenter')}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
              <circle cx="12" cy="12" r="5.5" /><path d="M12 2v3.5M12 18.5V22M2 12h3.5M18.5 12H22" />
            </svg>
          </button>
          <span className="cb-sep" />
          {CAM_VIEWS.map(({ v, tip, face }) => (
            <button key={v} className={camView === v ? 'on' : ''} data-tip={tip}
              onClick={() => { setCamView(v); refs.current?.setCam(v) }}>
              <CubeIcon face={face} />
            </button>
          ))}
          <span className="cb-sep" />
          <button className={rulerOn ? 'on' : ''} data-tip="Measure" onClick={() => setRulerOn((v) => !v)}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
              <rect x="2.5" y="8" width="19" height="8" rx="1" transform="rotate(-12 12 12)" />
              <path d="M7 8.5v2.4M11 7.7v3M15 6.9v2.4M19 6.1v3" transform="rotate(-12 12 12)" />
            </svg>
          </button>
          <div className="cb-vmenu">
            <button className={viewMenu ? 'on' : ''} data-tip="View options" onClick={() => setViewMenu((v) => !v)}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
                <path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6-10-6-10-6z" /><circle cx="12" cy="12" r="2.6" />
              </svg>
            </button>
            {viewMenu && (
              <div className="cb-pop" onPointerDown={(e) => e.stopPropagation()}>
                <label><input type="checkbox" checked={showGiz} onChange={(e) => setShowGiz(e.target.checked)} />Orientation gizmo</label>
                <label><input type="checkbox" checked={showGrid} onChange={(e) => setShowGrid(e.target.checked)} />Ground grid</label>
                <label><input type="checkbox" checked={showHuman} onChange={(e) => setShowHuman(e.target.checked)} />Human reference (1.8 m)</label>
              </div>
            )}
          </div>
        </div>
        {rulerOn && (() => {
          const d = rp.length === 2
            ? Math.hypot(rp[0][0] - rp[1][0], rp[0][1] - rp[1][1], rp[0][2] - rp[1][2]) : 0
          const fmt = (m: number) => (m >= 1 ? `${m.toFixed(3)} m` : `${(m * 100).toFixed(1)} cm`)
          return (
            <div className="ruler-panel" onPointerDown={(e) => e.stopPropagation()}>
              <div className="cap-head">
                <span className="cap-title">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
                    <rect x="2.5" y="8" width="19" height="8" rx="1" transform="rotate(-12 12 12)" />
                    <path d="M7 8.5v2.4M11 7.7v3M15 6.9v2.4M19 6.1v3" transform="rotate(-12 12 12)" />
                  </svg>Measure
                </span>
                <button className="cap-x" title="Done" onClick={() => setRulerOn(false)}>✕</button>
              </div>
              <div className="rl-body">
                {[0, 1].map((i) => (
                  <div className={`rl-pt${rSel === i ? ' on' : ''}`} key={i} onPointerDown={() => rp[i] && setRSel(i)}>
                    <span className="rl-tag">P{i + 1}</span>
                    {rp[i] ? (
                      <span className="vec">
                        {[0, 1, 2].map((ax) => (
                          <DragField key={ax} value={rp[i][ax]} min={-50} max={50} step={0.01} decimals={3} showFill={false}
                            prefix={<span style={{ color: AXIS[ax], fontWeight: 700 }}>{'XYZ'[ax]}</span>}
                            onChange={(v) => setRp((prev) => prev.map((c, j) => (j === i ? c.map((cc, k) => (k === ax ? v : cc)) : c)))} />
                        ))}
                      </span>
                    ) : <span className="rl-empty">click the view to place</span>}
                  </div>
                ))}
                <div className="rl-dist"><span className="rl-k">Distance</span><span className="rl-v mono">{rp.length === 2 ? fmt(d) : '—'}</span></div>
                <div className="rl-actions">
                  <button className="cap-cancel" disabled={!rp.length} onClick={() => { setRp([]); setRSel(-1) }}>Clear</button>
                  <button className="cap-go" onClick={() => setRulerOn(false)}>Done</button>
                </div>
              </div>
            </div>
          )
        })()}
        <div ref={hostRef} style={{ position: 'absolute', inset: 0 }} />
        {emptyMsg && <div className="emptyvp">{emptyMsg}</div>}
        {dropping && <div className="dropover"><Icon name="import" /><span>Drop to bake</span></div>}
        {overlays.has('gravity_field') && hasContent && pap && !capping && (
          <div className="inertia-info">
            <div className="ii-head"><Icon name="mass" /><span>Inertia</span></div>
            <div className="ii-row"><span className="ii-k">Mass</span><span className="ii-v">{pap.physical.mass_kg.toFixed(1)} kg</span></div>
            <div className="ii-row"><span className="ii-k">CoM height</span><span className="ii-v">{canonCom(pap.physical.com, name)[2].toFixed(3)} m</span></div>
            <div className="ii-row"><span className="ii-k">Gyration</span><span className="ii-v">{gyration(pap)}</span></div>
            <div className="ii-row"><span className="ii-k">Hollow</span><span className="ii-v">{pap.physical.hollow ? 'yes' : 'no'}</span></div>
          </div>
        )}

        {capping && hasContent && (
          <div className="cap-panel" onPointerDown={(e) => e.stopPropagation()}>
            <div className="cap-head">
              <span className="cap-title"><Icon name="seal" />Cap opening</span>
              <button className="cap-x" title="Done" onClick={() => onExitCap?.()}>✕</button>
            </div>
            <p className="cap-hint">Drag the handles to move the plane over a hole. The bright outline shows where it cuts, then place it down.</p>
            <div className="cap-field">
              <label>Handles</label>
              <div className="cap-axes">
                <button className={cap.mode === 'translate' ? 'on' : ''}
                  onClick={() => setCap((c) => ({ ...c, mode: 'translate' }))}>Move</button>
                <button className={cap.mode === 'rotate' ? 'on' : ''}
                  onClick={() => setCap((c) => ({ ...c, mode: 'rotate' }))}>Rotate</button>
              </div>
            </div>
            <div className="cap-field">
              <label>Lid size <span className="cap-num">{Math.round(cap.sizeFrac * 100)}%</span></label>
              <input type="range" min={0.05} max={1.2} step={0.01} value={cap.sizeFrac}
                onChange={(e) => setCap((c) => ({ ...c, sizeFrac: Number(e.target.value) }))} />
            </div>
            <div className="cap-actions">
              <button className="cap-cancel" onClick={() => onExitCap?.()} disabled={busy}>Cancel</button>
              <button className="cap-go" onClick={applyCap} disabled={busy}>{busy ? 'Capping…' : 'Place & cap'}</button>
            </div>
          </div>
        )}

        {capResult && !capping && hasContent && (
          <CapResultCard result={capResult} onAgain={() => onCapAgain?.()} onDone={() => onDismissCap?.()} />
        )}
      </div>
      {hasContent && (
        <MaskRail catalog={catalog} masks={masks} surface={surface} overlays={overlays}
          computing={computing} errors={maskErrors} onSurface={onSurface} onOverlay={onOverlay} />
      )}
      </div>
    </section>
  )
}

// Outcome card shown after auto-fill or a manual cap: did it seal / refine / find a shell
// / miss, plus mass & volume before → after so the effect is unambiguous.
const CR_META: Record<CapResult['status'], { cls: string; icon: string; title: string }> = {
  sealed: { cls: 'ok', icon: '✓', title: 'Sealed · watertight' },
  refined: { cls: 'ok', icon: '✓', title: 'Holes filled' },
  shell: { cls: 'shell', icon: '◐', title: 'Shell mesh' },
  none: { cls: 'warn', icon: '!', title: 'Nothing to seal' },
  error: { cls: 'err', icon: '✕', title: 'Cap failed' },
}
function CapResultCard({ result, onAgain, onDone }: { result: CapResult; onAgain: () => void; onDone: () => void }) {
  const { status, mode, before, after, watertight, message } = result
  const m = CR_META[status]
  const how = mode === 'auto' ? 'Auto-fill' : 'The cap'
  const sub = status === 'sealed' ? 'The solid is closed. Mass & volume are now exact.'
    : status === 'refined' ? `${how} closed some openings. Mass & volume updated; other open areas remain.`
    : status === 'shell' ? `This is a shell mesh (thin one-sided surfaces). ${mode === 'auto' ? 'Auto-fill can’t make it solid' : 'A patch was added, but the region stays a shell'}. Mass & volume are area-based, which is the correct model here.`
    : status === 'none' ? (mode === 'auto' ? 'No closeable openings were found.' : 'The plane didn’t cover a hole. Move or resize it over an opening, then try again.')
    : (message || 'The re-bake failed.')
  const dMass = after.mass - before.mass
  const dVol = (after.vol - before.vol) * 1000
  const wtLabel = status === 'shell' ? 'n/a · shell' : watertight ? 'yes · sealed' : 'no · still open'
  const row = (label: string, b: number, a: number, unit: string, d: number) => (
    <div className="cr-row">
      <span className="cr-k">{label}</span>
      <span className="cr-v">
        <span className="cr-was">{b.toFixed(1)}</span>
        <span className="cr-arr">→</span>
        <b>{a.toFixed(1)} {unit}</b>
        {Math.abs(d) >= 0.05 && <span className={`cr-d ${d >= 0 ? 'up' : 'dn'}`}>{d >= 0 ? '+' : ''}{d.toFixed(1)}</span>}
      </span>
    </div>
  )
  return (
    <div className={`cap-result ${m.cls}`} onPointerDown={(e) => e.stopPropagation()}>
      <div className="cr-head">
        <span className="cr-ico">{m.icon}</span>
        <span className="cr-title">{m.title}</span>
        <button className="cap-x" title="Dismiss" onClick={onDone}>✕</button>
      </div>
      <p className="cr-sub">{sub}</p>
      {status !== 'error' && (
        <div className="cr-stats">
          {row('Mass', before.mass, after.mass, 'kg', dMass)}
          {row('Volume', before.vol * 1000, after.vol * 1000, 'L', dVol)}
          <div className="cr-row">
            <span className="cr-k">Watertight</span>
            <span className={`cr-v ${watertight ? 'good' : ''}`}><b>{wtLabel}</b></span>
          </div>
        </div>
      )}
      <div className="cap-actions">
        <button className="cap-cancel" onClick={onDone}>Done</button>
        {status !== 'error' && status !== 'shell' && <button className="cap-go" onClick={onAgain}>Manual cap</button>}
        {status === 'shell' && <button className="cap-go" onClick={onAgain}>Manual cap anyway</button>}
      </div>
    </div>
  )
}

// An isometric cube whose highlighted face conveys the view (top / front / side);
// no face = the free perspective view.
type CubeFace = 'top' | 'left' | 'right' | 'none'
const FACE_PATH: Record<Exclude<CubeFace, 'none'>, string> = {
  top: 'M12,3.5 L20.5,8.25 L12,13 L3.5,8.25 Z',
  left: 'M3.5,8.25 L12,13 L12,20.5 L3.5,15.75 Z',
  right: 'M20.5,8.25 L12,13 L12,20.5 L20.5,15.75 Z',
}
function CubeIcon({ face }: { face: CubeFace }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round">
      {face !== 'none' && <path d={FACE_PATH[face]} fill="currentColor" fillOpacity="0.6" stroke="none" />}
      <path d="M12,3.5 L20.5,8.25 L20.5,15.75 L12,20.5 L3.5,15.75 L3.5,8.25 Z" />
      <path d="M3.5,8.25 L12,13 L20.5,8.25 M12,13 L12,20.5" />
    </svg>
  )
}
const CAM_VIEWS: { v: 'top' | 'front' | 'side' | 'persp'; tip: string; face: CubeFace }[] = [
  { v: 'top', tip: 'Top', face: 'top' },
  { v: 'front', tip: 'Front', face: 'left' },
  { v: 'side', tip: 'Side', face: 'right' },
  { v: 'persp', tip: 'Perspective', face: 'none' },
]

// glTF/glb bake in Y-up; the viewer stands the mesh up with rot.x=+90° (Y→Z). The
// baked CoM is in the file's native frame, so rotate it the same way to line the
// marker up with the mesh (no-op for already-Z-up obj/stl).
function canonCom(com: number[] | undefined, name: string): number[] {
  const c = com ?? [0, 0, 0]
  const e = (name.split('.').pop() || '').toLowerCase()
  return (e === 'gltf' || e === 'glb') ? [c[0] ?? 0, -(c[2] ?? 0), c[1] ?? 0] : [c[0] ?? 0, c[1] ?? 0, c[2] ?? 0]
}

// Per-axis radius of gyration k_i = sqrt(I_ii / m): how far from the CoM the mass
// effectively sits about each axis (bigger = harder to spin / topple that way).
function gyration(pap: PAP): string {
  const I = pap.physical.inertia, m = pap.physical.mass_kg
  if (!Array.isArray(I) || I.length !== 3 || !I.every((row) => Array.isArray(row) && row.length === 3) || !(m > 0)) return 'n/a'
  const k = (i: number) => Math.sqrt(Math.max(0, I[i][i] / m))
  return `${k(0).toFixed(2)} · ${k(1).toFixed(2)} · ${k(2).toFixed(2)} m`
}
