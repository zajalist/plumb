// Typed client for the PLUMB mask system. Mirrors cortex/masks/model.py.
const BASE = (import.meta as any).env?.VITE_API ?? 'http://localhost:8000'

export type Archetype = 'categorical' | 'scalar' | 'vector' | 'markers'
export type MaskSource = 'geometry' | 'hf' | 'gemini' | 'mcp'
export type MaskCategory = 'material' | 'physics' | 'artistic' | 'affordance' | 'custom'
export type MaskRole = 'surface' | 'overlay'

export type Region = { label: string; color: string; part_ids?: string[] }
export type MarkerPoint = { pos: number[]; label?: string; kind?: string }
export type MarkerLine = { a: number[]; b: number[]; label?: string }
export type MarkerAxis = { origin: number[]; dir: number[]; label?: string }

export type MaskData = {
  regions?: Region[]                                   // categorical
  per_part?: Record<string, number>; range?: number[]; ramp?: string; per_vertex?: Record<string, number[]>  // scalar
  samples?: { origin: number[]; vec: number[] }[]; field?: string  // vector
  points?: MarkerPoint[]; lines?: MarkerLine[]; axes?: MarkerAxis[]  // markers
}
export type MaskLegend =
  | { kind: 'swatches'; items: { label: string; color: string }[] }
  | { kind: 'ramp'; range: number[]; ramp: string }
  | { kind: 'none' }

export type Mask = {
  id: string; asset_id: string; name: string
  source: MaskSource; category: MaskCategory; archetype: Archetype; role: MaskRole
  data: MaskData; legend: MaskLegend
  confidence?: number | null; provider_key: string; version: number
}

export type MaskProviderMeta = {
  key: string; name: string; source: MaskSource; category: MaskCategory
  archetype: Archetype; role: MaskRole; needs_images: boolean; available: boolean
}

export async function maskProviders(): Promise<MaskProviderMeta[]> {
  const r = await fetch(`${BASE}/masks/providers`)
  if (!r.ok) throw new Error('mask providers failed')
  return (await r.json()).providers
}

export async function listMasks(assetId: string): Promise<Mask[]> {
  const r = await fetch(`${BASE}/masks/${encodeURIComponent(assetId)}`)
  if (!r.ok) throw new Error('list masks failed')
  return (await r.json()).masks
}

export async function computeMask(assetId: string, providerKey: string, images: Blob[] = []): Promise<Mask> {
  const fd = new FormData()
  fd.append('provider_key', providerKey)
  images.forEach((b, i) => fd.append('images', b, `render_${i}.png`))
  const r = await fetch(`${BASE}/masks/${encodeURIComponent(assetId)}/compute`, { method: 'POST', body: fd })
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? 'mask compute failed')
  return r.json()
}

export async function deleteMask(assetId: string, maskId: string): Promise<boolean> {
  const r = await fetch(`${BASE}/masks/${encodeURIComponent(assetId)}/${encodeURIComponent(maskId)}`, { method: 'DELETE' })
  if (!r.ok) return false
  return (await r.json()).ok
}
