import { Icon } from './Icons'

// Loose shape so this accepts both the live contract Verdict and the demo fixture.
type GateLike = { gate: string; ok: boolean | null; skipped: boolean; value_m: number | null }
type VerdictLike = { gates: GateLike[]; soft_cost: number; committed?: boolean } | null

const ORDER = ['collision', 'stability', 'constraints', 'reach'] as const

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
      <div className="gtitle"><Icon name="grid" /><span className="label" style={{ color: 'var(--ink2)' }}>Gate&nbsp;Stack</span></div>
      <div className="gflow">
        {ORDER.map((name, i) => {
          const g = by.get(name)
          const c = statusClass(g, verdict?.soft_cost ?? 0)
          const shown = g && !g.skipped && g.ok !== null
          return (
            <span key={name} style={{ display: 'contents' }}>
              <div className={`gate ${c}`}>
                <Icon name={name} />
                <span className="gn">{name}</span>
                <span className="gv">{shown ? cm(g!.value_m) : 'idle'}</span>
              </div>
              {i < ORDER.length - 1 && <span className="chev">›</span>}
            </span>
          )
        })}
      </div>
      <div className={`commitcell${verdict?.committed ? ' ready' : ''}`}>
        <Icon name="commit" /><span className="label">commit</span>
      </div>
    </div>
  )
}
