// Typed client for the PLUMB Studio backend. Types mirror the frozen contracts.py.
const BASE = (import.meta as any).env?.VITE_API ?? 'http://localhost:8000'

export type MaterialPart = { part: string; mat: string; conf: number }
export type PAP = {
  asset_id: string
  profile: string
  geometry: { obb: number[]; volume_m3: number; convex_parts: number; watertight: boolean }
  semantics: { cls: string; up: number[]; front: number[]; materials: MaterialPart[]; conf: number }
  physical: { mass_kg: number; com: number[]; inertia: number[][]; hollow: boolean; conf: number }
  structural: { support_footprint: number[][]; max_load_kg_est: number | null; experimental: boolean }
  rest_states: string[]
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
