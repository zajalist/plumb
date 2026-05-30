import type { ReactNode } from 'react'
import { Icon } from './Icons'
import type { PAP } from './api'

const SWATCH: Record<string, string> = {
  bronze: '#7b5a2a', stone: '#6b6a63', glass: '#5b6b6b', wood: '#6e5a36', default: '#5a5750',
}

export function Properties({ pap, footer }: { pap: PAP | null; footer?: ReactNode }) {
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
  return (
    <section className="pane props">
      <header>
        <div className="t"><Icon name="com" /><span>Properties — PAP</span></div>
        <span className="mono" style={{ fontSize: 10, color: 'var(--ink4)' }}>baked</span>
      </header>
      <div className="body">
        <div className="psec">
          <div className="label" style={{ marginBottom: 4 }}>Identity</div>
          <div className="prop"><span className="k">class</span><span className="v">{pap.semantics.cls}</span></div>
          <div className="prop"><span className="k"><Icon name="seal" />watertight</span><span className="v muted">{pap.geometry.watertight ? `yes · ${pap.geometry.convex_parts} parts` : 'no'}</span></div>
          <div className="prop"><span className="k"><Icon name="solid" />hollow</span><span className="v muted">{pap.physical.hollow ? 'yes' : 'no'}</span></div>
        </div>
        <div className="psec">
          <div className="label" style={{ marginBottom: 4 }}>Physics</div>
          <div className="prop"><span className="k"><Icon name="mass" />mass</span><span className="v">{pap.physical.mass_kg.toFixed(1)} kg</span></div>
          <div className="prop"><span className="k"><Icon name="com" />centre of mass</span><span className="v">{pap.physical.com.map(f3).join(', ')}</span></div>
          <div className="prop"><span className="k">volume</span><span className="v muted">{(pap.geometry.volume_m3 * 1000).toFixed(1)} L</span></div>
        </div>
        <div className="psec" style={{ borderBottom: 'none' }}>
          <div className="label">Materials <span style={{ color: 'var(--ink4)', textTransform: 'none', letterSpacing: 0 }}>— AI-guessed</span></div>
          <div className="mats">
            {pap.semantics.materials.length === 0 && (
              <div className="mat"><span className="ml"><span className="swatch" style={{ background: SWATCH.default }} />all parts</span><span className="mr">default</span></div>
            )}
            {pap.semantics.materials.map((m) => (
              <div className="mat" key={m.part}>
                <span className="ml"><span className="swatch" style={{ background: SWATCH[m.mat] ?? SWATCH.default }} />{m.part}</span>
                <span className="mr">{m.mat} · {m.conf.toFixed(2)}</span>
              </div>
            ))}
          </div>
          <div className="confirm"><Icon name="lock" />Confirm &amp; lock materials</div>
        </div>
        {footer}
      </div>
    </section>
  )
}
