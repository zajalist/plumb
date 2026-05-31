// Typed client for the PLUMB Studio backend. Types mirror the frozen contracts.py.
const BASE = (import.meta as any).env?.VITE_API ?? 'http://localhost:8000'

export type MaterialPart = { part: string; mat: string; conf: number }
// A baked per-part mask (augmented /bake field, outside the frozen contract).
export type Part = {
  id: string; idx: number
  material: string; conf: number; source: string; confirmed: boolean
  volume_m3: number; vol_frac: number; mass_kg: number; mass_frac: number
  hollow: boolean; centroid: number[]; extent: number[]; color: string
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
export type Health = { ok: boolean; cortex: boolean }

export async function health(): Promise<Health> {
  const r = await fetch(`${BASE}/health`)
  return r.json()
}

export async function bake(file: File, materials?: Record<string, string>): Promise<PAP> {
  const fd = new FormData()
  fd.append('mesh', file)
  if (materials) fd.append('materials', JSON.stringify(materials))
  const r = await fetch(`${BASE}/bake`, { method: 'POST', body: fd })
  if (!r.ok) {
    const detail = await r.json().catch(() => ({}))
    throw new Error(detail.detail ?? 'bake failed')
  }
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
export const validate = (object: string, pos: number[], quat = DEFAULT_QUAT) =>
  post<Verdict>('/validate', { object, pos, quat })
export const repair = (object: string, pos: number[], quat = DEFAULT_QUAT) =>
  post<Tf>('/repair', { object, pos, quat })
export const commit = (object: string, pos: number[], quat = DEFAULT_QUAT) =>
  post<{ ok: boolean }>('/commit', { object, pos, quat })
