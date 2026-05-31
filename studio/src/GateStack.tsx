import { GateIcon3D, type GateShape } from './GateIcon3D'

// Loose shape so this accepts both the live contract Verdict and the demo fixture.
type GateLike = { gate: string; ok: boolean | null; skipped: boolean; value_m: number | null }
type VerdictLike = { gates: GateLike[]; soft_cost: number; committed?: boolean } | null

const ORDER = ['collision', 'stability', 'constraints', 'reach'] as const

// status → the colour the 3D icon tints to (matches theme.css gate semantics)
const TINT: Record<string, string> = {
  idle: '#7E8A98', pass: '#34C0AD', fail: '#E0694F', soft: '#D9A84C',
}

function statusClass(g: GateLike | undefined, soft: number): string {
  if (!g || g.skipped || g.ok === null) return 'idle'
  if (g.ok === false) return 'fail'
  if (g.gate === 'constraints' && soft > 1.0) return 'soft'
  return 'pass'
}
const cm = (m: number | null) => (m === null ? 'idle' : `${m >= 0 ? '+' : '−'}${Math.abs(m * 100).toFixed(1)} cm`)

export function GateStack({ verdict }: { verdict: VerdictLike }) {
  const by = new Map((verdict?.gates ?? []).map((g) => [g.gate, g]))
  return (
    <div className="gates">
      <div className="gtitle"><span className="label">Gate&nbsp;Stack</span></div>
      <div className="gflow">
        {ORDER.map((name) => {
          const g = by.get(name)
          const c = statusClass(g, verdict?.soft_cost ?? 0)
          const shown = g && !g.skipped && g.ok !== null
          return (
            <div key={name} className={`gate ${c}`}>
              <GateIcon3D shape={name as GateShape} color={TINT[c]} />
              <span className="gn">{name}</span>
              {shown && <span className="gv">{cm(g!.value_m)}</span>}
            </div>
          )
        })}
      </div>
      <div className={`commitcell${verdict?.committed ? ' ready' : ''}`}>
        <GateIcon3D shape="commit" color={verdict?.committed ? '#34C0AD' : '#7E8A98'} />
        <span className="label">commit</span>
      </div>
    </div>
  )
}
