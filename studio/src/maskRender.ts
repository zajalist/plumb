// Pure three.js helpers for painting masks onto the convex-part representation and
// building overlay objects. Kept out of Viewport.tsx so the colour/ramp logic is testable
// and the component stays focused. Groups are the viewport's part groups (name = part id).
import * as THREE from 'three'
import type { MaskData } from './masks'

export type ColorGroup = { name: string; meshes: THREE.Mesh[] }

const RAMPS: Record<string, string[]> = {
  plasma: ['#0d0887', '#7e03a8', '#cc4778', '#f89540', '#f0f921'],
  magma: ['#000004', '#51127c', '#b73779', '#fc8961', '#fcfdbf'],
  inferno: ['#000004', '#56106e', '#bb3754', '#f98c0a', '#fcffa4'],
  viridis: ['#440154', '#3b528b', '#21918c', '#5ec962', '#fde725'],
}
const KIND_COLOR: Record<string, number> = {
  grasp: 0xc08ad0, contact: 0xd9a84c, affordance: 0x34c0ad, support: 0xe0694f, default: 0x9fe6da,
}
const NEUTRAL = new THREE.Color('#3a4348')

export function rampColor(t: number, ramp = 'plasma'): THREE.Color {
  const stops = RAMPS[ramp] ?? RAMPS.plasma
  const x = Math.max(0, Math.min(1, t)) * (stops.length - 1)
  const i = Math.min(stops.length - 2, Math.floor(x))
  return new THREE.Color(stops[i]).lerp(new THREE.Color(stops[i + 1]), x - i)
}

function paint(g: ColorGroup, color: THREE.Color) {
  for (const m of g.meshes) {
    const mm = (m.userData.maskMat ||= new THREE.MeshStandardMaterial({ roughness: 0.85, metalness: 0.04 }))
    mm.color.copy(color)
    m.material = mm
  }
}

// Resolve a per-part value for each group: match by part id, else fall back to index order
// (the model's material groups and the bake's parts enumerate the same materials in order).
function resolve<T>(groups: ColorGroup[], keyed: Record<string, T>): (T | undefined)[] {
  const keys = Object.keys(keyed)
  const byName = groups.some((g) => g.name in keyed)
  return byName ? groups.map((g) => keyed[g.name]) : groups.map((_, i) => keyed[keys[i]])
}

export function applyCategorical(groups: ColorGroup[], regions: MaskData['regions'] = []) {
  const byPart: Record<string, string> = {}
  for (const r of regions) for (const pid of r.part_ids ?? []) byPart[pid] = r.color
  const colors = resolve(groups, byPart)
  groups.forEach((g, i) => paint(g, colors[i] ? new THREE.Color(colors[i]) : NEUTRAL))
}

export function applyScalar(groups: ColorGroup[], perPart: Record<string, number> = {},
                            range: number[] = [0, 1], ramp = 'plasma') {
  const [lo, hi] = range
  const span = hi - lo || 1
  const vals = resolve(groups, perPart)
  groups.forEach((g, i) => paint(g, vals[i] == null ? NEUTRAL : rampColor((vals[i]! - lo) / span, ramp)))
}

// Overlay objects (markers / axes). Positions are canonical (parent supplies the frame).
export function buildMarkers(data: MaskData, scale = 1): THREE.Group {
  const grp = new THREE.Group()
  const r = Math.max(0.012, scale * 0.03)
  for (const p of data.points ?? []) {
    const col = KIND_COLOR[p.kind ?? 'default'] ?? KIND_COLOR.default
    const dot = new THREE.Mesh(new THREE.SphereGeometry(r, 16, 16),
      new THREE.MeshBasicMaterial({ color: col }))
    dot.position.set(p.pos[0] ?? 0, p.pos[1] ?? 0, p.pos[2] ?? 0)
    grp.add(dot)
  }
  for (const l of data.lines ?? []) {
    const geo = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(...(l.a as [number, number, number])),
      new THREE.Vector3(...(l.b as [number, number, number]))])
    grp.add(new THREE.Line(geo, new THREE.LineBasicMaterial({ color: 0x34c0ad })))
  }
  for (const ax of data.axes ?? []) {
    const o = new THREE.Vector3(...(ax.origin as [number, number, number]))
    const d = new THREE.Vector3(...(ax.dir as [number, number, number])).normalize().multiplyScalar(scale)
    const geo = new THREE.BufferGeometry().setFromPoints([o.clone().sub(d), o.clone().add(d)])
    grp.add(new THREE.Line(geo, new THREE.LineDashedMaterial({ color: 0x5c8bd6, dashSize: scale * 0.08, gapSize: scale * 0.05 })))
  }
  grp.traverse((o) => { const ln = o as THREE.Line; if ((ln as any).computeLineDistances) ln.computeLineDistances?.() })
  return grp
}

export function buildVectorSamples(data: MaskData, color = 0x5c8bd6): THREE.Group {
  const grp = new THREE.Group()
  for (const s of data.samples ?? []) {
    const dir = new THREE.Vector3(...(s.vec as [number, number, number]))
    const len = dir.length() || 1
    grp.add(new THREE.ArrowHelper(dir.clone().normalize(),
      new THREE.Vector3(...(s.origin as [number, number, number])), len, color, len * 0.3, len * 0.2))
  }
  return grp
}
