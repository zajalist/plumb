import { useEffect, useState, type ReactNode } from 'react'
import { Icon } from './Icons'
import type { PAP } from './api'

const SWATCH: Record<string, string> = {
  bronze: '#7b5a2a', stone: '#6b6a63', glass: '#5b6b6b', wood: '#6e5a36', default: '#5a5750',
}
const MATERIALS = ['default', 'bronze', 'stone', 'glass', 'wood']

export function Properties({ pap, footer, onConfirm, busy }: {
  pap: PAP | null
  footer?: ReactNode
  onConfirm?: (materials: Record<string, string>) => void
  busy?: boolean
}) {
  // per-part material overrides (idx -> material), reset when the asset changes
  const [over, setOver] = useState<Record<number, string>>({})
  useEffect(() => { setOver({}) }, [pap?.asset_id])

  if (!pap) {
    return (
      <section className="pane props">
        <header><div className="t"><Icon name="com" /><span>Properties — PAP</span></div></header>
        <div className="body" style={{ padding: 16, color: 'var(--ink3)', fontSize: 13 }}>
          Import or select an asset to bake.
        </div>
      </section>
    )
  }
  const f3 = (n: number) => (n.toFixed(2).replace(/^(-?)0\./, '$1.'))
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
        <div className="t"><Icon name="com" /><span>Properties — PAP</span></div>
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
          <div className="label" style={{ marginBottom: 4 }}>Physics</div>
          <div className="prop"><span className="k"><Icon name="mass" />mass</span><span className="v">{pap.physical.mass_kg.toFixed(1)} kg</span></div>
          <div className="prop"><span className="k"><Icon name="com" />centre of mass</span><span className="v">{pap.physical.com.map(f3).join(', ')}</span></div>
          <div className="prop"><span className="k">volume</span><span className="v muted">{(pap.geometry.volume_m3 * 1000).toFixed(1)} L</span></div>
        </div>
        <div className="psec" style={{ borderBottom: 'none' }}>
          <div className="label">
            Parts <span style={{ color: 'var(--ink4)', textTransform: 'none', letterSpacing: 0 }}>
              {allConfirmed ? '— masks · locked' : `— ${parts.length || 'no'} masks · AI-guessed`}
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
