import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Icon } from './Icons'
import { DragField } from './DragField'
import { SearchSelect } from './SearchSelect'
import { MATERIAL_OPTIONS, MATERIAL_SWATCH } from './lib/bakeCatalog'
import type { PAP, WdfAsset } from './api'

// usual axis colour codes (X red · Y green · Z blue), palette-harmonised
const AXIS = ['#E0694F', '#6FBF73', '#5C8BD6']

const SWATCH: Record<string, string> = {
  bronze: '#7b5a2a', stone: '#6b6a63', glass: '#5b6b6b', wood: '#6e5a36', default: '#5a5750',
  foliage: '#566b38', metal: '#8a8d92', plastic: '#585866', fabric: '#6a5a48', water: '#3a5a6a',
}
const MASK_PALETTE = ['#34C0AD', '#D9A84C', '#6E8BA0', '#E0694F', '#5FA38C', '#A088B0', '#C2925A', '#7C8AA0']
// swatch / display label for a material value (catalog first, legacy fallback)
const matSwatch = (m: string) => MATERIAL_SWATCH[m] ?? SWATCH[m] ?? SWATCH.default
const matLabel = (m: string) => (MATERIAL_OPTIONS.find((o) => o.value === m)?.label ?? m)

export function Properties({ pap, footer, onConfirm, onCapOpenings, onAutoFill, capping, onEditPap, scale, onScale, busy, declared }: {
  pap: PAP | null
  footer?: ReactNode
  onConfirm?: (materials: Record<string, string>) => void
  onCapOpenings?: () => void   // launch the manual cap-plane tool in the viewport
  onAutoFill?: () => void      // one-click auto hole-fill of the closeable solids
  capping?: boolean            // the cap tool is currently active
  // manual physics override — patches the PAP so the viewport updates live
  onEditPap?: (patch: { physical?: Partial<PAP['physical']>; geometry?: Partial<PAP['geometry']> }) => void
  scale?: number               // uniform placement scale (drives the viewport + validation)
  onScale?: (s: number) => void
  busy?: boolean
  declared?: WdfAsset       // an asset declared by an opened .wdf (no bake yet)
}) {
  // per-part material overrides (idx -> material), reset when the asset changes
  const [over, setOver] = useState<Record<number, string>>({})
  // stable fill-bar maxima captured per asset (so live mass/volume edits don't move the goalposts)
  const baseRef = useRef({ mass: 200, vol: 100 })
  useEffect(() => {
    setOver({})
    if (pap) baseRef.current = { mass: Math.max(200, pap.physical.mass_kg * 2), vol: Math.max(100, pap.geometry.volume_m3 * 1000 * 2) }
  }, [pap?.asset_id])

  if (!pap && declared) {
    const masks = Object.entries(declared.material)
    const meta = (k: string, v: string) => (
      <div className="prop"><span className="k">{k}</span><span className="v muted">{v}</span></div>
    )
    return (
      <section className="pane props">
        <header>
          <div className="t"><Icon name="com" /><span>Properties</span></div>
          <span className="mono" style={{ fontSize: 10, color: 'var(--ink4)' }}>.wdf</span>
        </header>
        <div className="body">
          <div className="psec">
            <div className="label" style={{ marginBottom: 4 }}>Identity</div>
            <div className="prop"><span className="k">profile</span><span className="v">{declared.profile ?? '·'}</span></div>
            {declared.states.length > 0 && meta('states', declared.states.join(' · '))}
            {declared.tags.length > 0 && meta('tags', declared.tags.join(' · '))}
            {declared.joint && meta('joint', `${declared.joint.axis} ${declared.joint.range_min}-${declared.joint.range_max}°`)}
            {declared.swept_volume && meta('swept', declared.swept_volume)}
            {declared.load_cap && meta('load cap', declared.load_cap)}
          </div>
          <div className="psec" style={{ borderBottom: 'none' }}>
            <div className="label">Masks <span style={{ color: 'var(--ink4)', textTransform: 'none', letterSpacing: 0 }}>{masks.length}</span></div>
            <div className="masks">
              {masks.map(([part, mat], i) => (
                <div className="mask" key={part}>
                  <span className="mask-c" style={{ background: MASK_PALETTE[i % MASK_PALETTE.length] }} />
                  <div className="mask-main">
                    <div className="mask-top">
                      <span className="mask-id mono">{part}</span>
                      <span className="mask-mat"><span className="swatch" style={{ background: SWATCH[mat] ?? SWATCH.default }} />{mat}</span>
                      <span className="mask-conf mono">declared</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
            {declared.affordances.length > 0 && (
              <div className="label" style={{ marginTop: 14 }}>Affordances <span style={{ color: 'var(--ink3)', textTransform: 'none', letterSpacing: 0, fontWeight: 400 }}>{declared.affordances.join(' · ')}</span></div>
            )}
          </div>
        </div>
      </section>
    )
  }

  if (!pap) {
    return (
      <section className="pane props">
        <header><div className="t"><Icon name="com" /><span>Properties</span></div></header>
        <div className="body" style={{ padding: 16, color: 'var(--ink3)', fontSize: 13 }}>
          Import or select an asset to bake.
        </div>
      </section>
    )
  }
  const parts = pap.parts ?? []
  const allConfirmed = parts.length > 0 && parts.every((p) => p.confirmed)

  // Closure assessment: are there closeable solid openings, or is this an area-based
  // shell (foliage/cloth/one-sided)? Drives the auto-fill / manual-cap UX + messaging.
  const solids = parts.filter((p) => !p.shell)
  const openSolids = solids.filter((p) => p.hollow).length
  const shellMesh = parts.length > 0 && solids.length === 0
  const closed = pap.geometry.watertight || (solids.length > 0 && openSolids === 0)
  const clState = closed ? 'ok' : shellMesh ? 'shell' : 'open'

  const confirm = () => {
    if (!onConfirm) return
    const map: Record<string, string> = {}
    for (const p of parts) map[String(p.idx)] = over[p.idx] ?? p.material
    onConfirm(map)
  }

  return (
    <section className="pane props">
      <header>
        <div className="t"><Icon name="com" /><span>Properties</span></div>
        <span className="mono" style={{ fontSize: 10, color: 'var(--ink4)' }}>{allConfirmed ? 'locked' : 'baked'}</span>
      </header>
      <div className="body">
        <div className="psec">
          <div className="label" style={{ marginBottom: 4 }}>Identity</div>
          <div className="prop"><span className="k">class</span><span className="v">{pap.semantics.cls}</span></div>
          <div className="prop"><span className="k"><Icon name="seal" />watertight</span><span className="v muted">{pap.geometry.watertight ? `yes · ${pap.geometry.convex_parts} parts` : `no · ${pap.geometry.convex_parts} parts`}</span></div>
          <div className="prop"><span className="k"><Icon name="solid" />hollow</span><span className="v muted">{pap.physical.hollow ? 'yes' : 'no'}</span></div>
        </div>
        <div className="psec">
          <div className="label" style={{ marginBottom: 4 }}>Semantics</div>
          {pap.semantics.conf != null && (() => {
            const pct = Math.round(pap.semantics.conf * 100)
            const grade = pct >= 80 ? 'hi' : pct >= 50 ? 'mid' : 'lo'
            return (
              <div className="prop conf-prop">
                <span className="k">confidence</span>
                <span className="conf-meter">
                  <span className="conf-bar"><span className={`conf-fill ${grade}`} style={{ width: `${pct}%` }} /></span>
                  <span className={`conf-pct mono ${grade}`}>{pct}%</span>
                </span>
              </div>
            )
          })()}
          <div className="prop"><span className="k">up</span><span className="v muted mono">[{pap.semantics.up.map((n) => n.toFixed(1)).join(', ')}]</span></div>
          <div className="prop"><span className="k">front</span><span className="v muted mono">[{pap.semantics.front.map((n) => n.toFixed(1)).join(', ')}]</span></div>
          {(pap.semantics.affordances?.length ?? 0) > 0 && (
            <div className="aff-chips">
              {(pap.semantics.affordances ?? []).map((a: string) => <span className="aff-chip" key={a}>{a}</span>)}
            </div>
          )}
        </div>
        {!closed && (
          <div className={`closure ${clState}`}>
            <div className="cl-top">
              <span className="cl-ico">{clState === 'shell' ? '◐' : '!'}</span>
              <div className="cl-body">
                <div className="cl-t">{shellMesh ? 'Shell mesh' : 'Open surface'}</div>
                <div className="cl-d">
                  {shellMesh
                    ? <>Thin one-sided surfaces (foliage / cloth). Mass &amp; volume are <b>area-based</b> — the correct model for shells, not a defect. Sealing can’t make it solid.</>
                    : <>{openSolids > 0 ? `${openSolids} solid region${openSolids > 1 ? 's have' : ' has'} an opening. ` : 'Open surfaces. '}Mass &amp; volume are <b>estimated</b> — fill the holes for exact values.</>}
                </div>
              </div>
            </div>
            <div className="cl-actions">
              {onAutoFill && (
                <button className="cl-auto" disabled={busy || shellMesh} onClick={onAutoFill}
                  title={shellMesh ? 'No closeable openings — this is a shell mesh' : 'Fill every closeable hole automatically'}>
                  {busy ? 'Filling…' : 'Auto-fill holes'}
                </button>
              )}
              {onCapOpenings && (
                <button className={`cl-manual${capping ? ' on' : ''}`} disabled={busy} onClick={onCapOpenings}
                  title="Place a plane over a specific opening yourself">
                  {capping ? 'Placing…' : 'Manual cap'}
                </button>
              )}
            </div>
            {shellMesh && <div className="cl-note">Auto-fill is off — there’s nothing solid to seal. Use manual only to force-close a specific opening.</div>}
          </div>
        )}
        <div className="psec">
          <div className="label" style={{ marginBottom: 4 }}>Physics</div>
          <div className="prop">
            <span className="k"><Icon name="mass" />mass</span>
            <DragField value={pap.physical.mass_kg} onChange={(v) => onEditPap?.({ physical: { mass_kg: v } })}
              min={0} max={baseRef.current.mass} step={0.5} decimals={1} unit="kg" />
          </div>
          <div className="prop">
            <span className="k"><Icon name="com" />centre of mass</span>
            <span className="vec">
              {pap.physical.com.map((c, i) => (
                <DragField key={i} value={c} min={-2} max={2} step={0.01} decimals={2} showFill={false}
                  prefix={<span style={{ color: AXIS[i], fontWeight: 700 }}>{'XYZ'[i]}</span>}
                  onChange={(v) => { const next = [...pap.physical.com]; next[i] = v; onEditPap?.({ physical: { com: next } }) }} />
              ))}
            </span>
          </div>
          <div className="prop">
            <span className="k">volume</span>
            <DragField value={pap.geometry.volume_m3 * 1000} onChange={(v) => onEditPap?.({ geometry: { volume_m3: v / 1000 } })}
              min={0} max={baseRef.current.vol} step={0.5} decimals={1} unit="L" />
          </div>
          {onScale && (
            <>
              <div className="prop">
                <span className="k"><Icon name="grid" />scale</span>
                <DragField value={scale ?? 1} onChange={(v) => onScale(v)}
                  min={0.05} max={5} step={0.01} decimals={2} unit="×" />
              </div>
              <div className="prop">
                <span className="k">size</span>
                <span className="v muted mono">
                  {(() => {
                    const s = scale ?? 1, o = pap.geometry.obb
                    const dims = [o?.[0] ?? 0, o?.[1] ?? 0, o?.[2] ?? 0].map((h) => h * 2 * s)
                    const tall = Math.max(...dims)
                    return `${dims.map((d) => d.toFixed(2)).join(' × ')} m · ${tall.toFixed(2)} m tall`
                  })()}
                </span>
              </div>
            </>
          )}
        </div>
        <div className="psec" style={{ borderBottom: 'none' }}>
          <div className="label">
            Parts <span style={{ color: 'var(--ink4)', textTransform: 'none', letterSpacing: 0 }}>
              {allConfirmed ? 'locked' : `${parts.length || 'no'} masks`}
            </span>
          </div>

          {parts.length === 0 ? (
            <div className="mats">
              {pap.semantics.materials.length === 0 ? (
                <div className="mat"><span className="ml"><span className="swatch" style={{ background: SWATCH.default }} />all parts</span><span className="mr">default</span></div>
              ) : pap.semantics.materials.map((m) => (
                <div className="mat" key={m.part}>
                  <span className="ml"><span className="swatch" style={{ background: SWATCH[m.mat] ?? SWATCH.default }} />{m.part}</span>
                  <span className="mr">{m.mat} · {m.conf.toFixed(2)}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="masks">
              {parts.map((p) => {
                const mat = over[p.idx] ?? p.material
                return (
                  <div className="mask" key={p.id}>
                    <span className="mask-c" style={{ background: p.color }} title={p.id} />
                    <div className="mask-main">
                      <div className="mask-top">
                        <span className="mask-id mono">{p.id}{p.hollow ? ' · shell' : ''}</span>
                        {p.confirmed || !onConfirm ? (
                          <span className="mask-mat"><span className="swatch" style={{ background: matSwatch(mat) }} />{matLabel(mat)}</span>
                        ) : (
                          <SearchSelect value={mat} options={MATERIAL_OPTIONS} disabled={busy}
                            placeholder="Search materials…"
                            onChange={(v) => setOver((o) => ({ ...o, [p.idx]: v }))} />
                        )}
                        <span className="mask-conf mono">{p.confirmed ? 'locked' : `${Math.round(p.conf * 100)}%`}</span>
                      </div>
                      <div className="mask-bar"><span style={{ width: `${Math.max(3, Math.round(p.vol_frac * 100))}%`, background: p.color }} /></div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}

          {!allConfirmed && onConfirm && parts.length > 0 && (
            <button className="confirm" disabled={busy} onClick={confirm}>
              <Icon name="lock" />{busy ? 'Applying…' : 'Confirm & lock materials'}
            </button>
          )}
        </div>
        {footer}
      </div>
    </section>
  )
}
