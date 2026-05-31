import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Icon } from './Icons'
import { DragField } from './DragField'
import type { PAP, WdfAsset } from './api'

// usual axis colour codes (X red · Y green · Z blue), palette-harmonised
const AXIS = ['#E0694F', '#6FBF73', '#5C8BD6']

const SWATCH: Record<string, string> = {
  bronze: '#7b5a2a', stone: '#6b6a63', glass: '#5b6b6b', wood: '#6e5a36', default: '#5a5750',
  foliage: '#566b38', metal: '#8a8d92', plastic: '#585866', fabric: '#6a5a48', water: '#3a5a6a',
}
const MASK_PALETTE = ['#34C0AD', '#D9A84C', '#6E8BA0', '#E0694F', '#5FA38C', '#A088B0', '#C2925A', '#7C8AA0']
const MATERIALS = ['default', 'wood', 'foliage', 'stone', 'metal', 'glass', 'plastic', 'fabric', 'bronze', 'water']

export function Properties({ pap, footer, onConfirm, onCapOpenings, capping, onEditPap, busy, declared }: {
  pap: PAP | null
  footer?: ReactNode
  onConfirm?: (materials: Record<string, string>) => void
  onCapOpenings?: () => void   // launch the manual cap-plane tool in the viewport
  capping?: boolean            // the cap tool is currently active
  // manual physics override — patches the PAP so the viewport updates live
  onEditPap?: (patch: { physical?: Partial<PAP['physical']>; geometry?: Partial<PAP['geometry']> }) => void
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
        {!pap.geometry.watertight && (
          <div className="wt-warn">
            <span className="wt-ico">!</span>
            <div className="wt-body">
              <div className="wt-t">Mesh is not closed</div>
              <div className="wt-d">Open surfaces — mass &amp; volume are <b>estimated</b>. Place a cap plane over an opening to compute true values.</div>
            </div>
            {onCapOpenings && (
              <button className={`wt-cap${capping ? ' on' : ''}`} disabled={busy} onClick={onCapOpenings}>
                {capping ? 'Placing…' : 'Cap openings'}
              </button>
            )}
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
                          <span className="mask-mat"><span className="swatch" style={{ background: SWATCH[mat] ?? SWATCH.default }} />{mat}</span>
                        ) : (
                          <select className="mask-sel" value={mat} disabled={busy}
                            onChange={(e) => setOver((o) => ({ ...o, [p.idx]: e.target.value }))}>
                            {MATERIALS.map((m) => <option key={m} value={m}>{m}</option>)}
                          </select>
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
