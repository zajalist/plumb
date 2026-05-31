// Typed client for the PLUMB Studio backend. Types mirror the frozen contracts.py.
const BASE = (import.meta as any).env?.VITE_API ?? 'http://localhost:8000'

export type MaterialPart = { part: string; mat: string; conf: number }
// A baked per-part mask (augmented /bake field, outside the frozen contract).
export type Part = {
  id: string; idx: number
  material: string; conf: number; source: string; confirmed: boolean
  volume_m3: number; vol_frac: number; mass_kg: number; mass_frac: number
  hollow: boolean; centroid: number[]; extent: number[]; color: string
  verts?: number[][]; tris?: number[][]   // convex-part geometry for the masks view
}
export type PAP = {
  asset_id: string
  profile: string
  geometry: { obb: number[]; volume_m3: number; convex_parts: number; watertight: boolean }
  semantics: { cls: string; up: number[]; front: number[]; materials: MaterialPart[]; conf: number }
  physical: { mass_kg: number; com: number[]; inertia: number[][]; hollow: boolean; conf: number }
  structural: { support_footprint: number[][]; max_load_kg_est: number | null; experimental: boolean }
  provenance?: { auto: boolean; edited_fields: string[]; locked: string[] }
  rest_states: string[]
  parts?: Part[]
}
export type Health = {
  ok: boolean; cortex: boolean
  ue?: { available: boolean; cmd: boolean; project: boolean }
  gemini?: { available: boolean; sdk: boolean; key: boolean }
}

// AI semantic bake (Gemini): what the asset IS — class, up/front, region materials, affordances.
export type AiSemantics = {
  class?: string; up?: number[]; front?: number[]
  materials?: { region: string; material: string }[]
  affordances?: string[]; confidence?: number; raw?: string
}
export async function semanticBake(assetId: string, images: Blob[], hint = ''): Promise<AiSemantics> {
  const fd = new FormData()
  fd.append('asset_id', assetId)
  fd.append('hint', hint)
  images.forEach((b, i) => fd.append('images', b, `render_${i}.png`))
  const r = await fetch(`${BASE}/semantics`, { method: 'POST', body: fd })
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? 'semantics failed')
  return r.json()
}

export async function health(): Promise<Health> {
  const r = await fetch(`${BASE}/health`)
  return r.json()
}

export type BakeOpts = { materials?: Record<string, string>; profile?: string; decimate?: number; cap?: boolean; extras?: File[] }

export async function bake(file: File, opts: BakeOpts = {}): Promise<PAP> {
  const fd = new FormData()
  fd.append('mesh', file)
  if (opts.materials) fd.append('materials', JSON.stringify(opts.materials))
  if (opts.profile) fd.append('profile', opts.profile)
  if (opts.decimate) fd.append('decimate', String(opts.decimate))
  if (opts.cap) fd.append('cap', 'true')
  for (const e of opts.extras ?? []) fd.append('extras', e)
  const r = await fetch(`${BASE}/bake`, { method: 'POST', body: fd })
  if (!r.ok) {
    const detail = await r.json().catch(() => ({}))
    throw new Error(detail.detail ?? 'bake failed')
  }
  return r.json()
}

// Batch-convert .uasset files in ONE Unreal boot, then bake each by token.
export type ConvertResult = { name: string; token: string | null; ok: boolean }
export async function convertUassets(files: File[]): Promise<ConvertResult[]> {
  const fd = new FormData()
  for (const f of files) fd.append('files', f)
  const r = await fetch(`${BASE}/convert`, { method: 'POST', body: fd })
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? 'convert failed')
  return (await r.json()).results
}

export async function bakeCached(token: string, opts: BakeOpts = {}): Promise<PAP> {
  const r = await fetch(`${BASE}/bake_cached`, {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ token, materials: opts.materials, profile: opts.profile, decimate: opts.decimate }),
  })
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? 'bake failed')
  return r.json()
}

// --- validate / repair / commit (the live gate loop) ---
export type GateName = 'collision' | 'stability' | 'constraints' | 'reach'
export type GateResult = {
  gate: GateName
  ok: boolean | null
  skipped: boolean
  value_m: number | null
  fix: { translate: number[]; rotate_quat: number[] | null } | null
  viz: string | null
  detail: string | null
}
export type Verdict = { ok: boolean; stopped_at: GateName | null; gates: GateResult[]; soft_cost: number }
export type Tf = { pos: number[]; quat: number[]; scale: number[] }

async function post<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body),
  })
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? `${path} failed`)
  return r.json()
}

const DEFAULT_QUAT = [0, 0, 0, 1]
// --- .wdf scene (open a world document) ---
export type WdfJoint = { axis: string; range_min: number; range_max: number }
export type WdfAsset = {
  name: string; profile: string | null; material: Record<string, string>
  states: string[]; affordances: string[]; tags: string[]
  joint: WdfJoint | null; swept_volume: string | null; load_cap: string | null
}
export type WdfLaw = { name: string; expr: string; hard: boolean }
export type WdfPlacement = { asset: string; target: string; preposition: string; state: string | null }
export type WdfField = { key: string; value: string }
export type WdfScene = { name: string; fields: WdfField[]; placements: WdfPlacement[]; laws: WdfLaw[] }
export type WdfDoc = { vocabulary: { assets: WdfAsset[] }; scene: WdfScene | null }

export async function openWdf(file: File): Promise<WdfDoc> {
  const fd = new FormData()
  fd.append('doc', file)
  const r = await fetch(`${BASE}/open_wdf`, { method: 'POST', body: fd })
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? 'open .wdf failed')
  return r.json()
}

export const validate = (object: string, pos: number[], quat = DEFAULT_QUAT) =>
  post<Verdict>('/validate', { object, pos, quat })
export const repair = (object: string, pos: number[], quat = DEFAULT_QUAT) =>
  post<Tf>('/repair', { object, pos, quat })
export const commit = (object: string, pos: number[], quat = DEFAULT_QUAT) =>
  post<{ ok: boolean }>('/commit', { object, pos, quat })
