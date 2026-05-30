import { Icon } from './Icons'
import type { Attempt, Gate } from './verdicts'

const ORDER: Gate['gate'][] = ['collision', 'stability', 'constraints', 'reach']

function statusClass(g: Gate | undefined, soft: number): string {
  if (!g || g.skipped || g.ok === null) return 'idle'
  if (g.ok === false) return 'fail'
  if (g.gate === 'constraints' && soft > 1.0) return 'soft'
  return 'pass'
}

const cm = (m: number | null) => (m === null ? 'idle' : `${m >= 0 ? '+' : '−'}${Math.abs(m * 100).toFixed(1)} cm`)

export function GateStack({ attempt }: { attempt: Attempt | null }) {
  const by = new Map((attempt?.gates ?? []).map((g) => [g.gate, g]))
  return (
    <div className="gates">
      <div className="gtitle"><Icon name="grid" /><span className="label" style={{ color: 'var(--ink2)' }}>Gate&nbsp;Stack</span></div>
      <div className="gflow">
        {ORDER.map((name, i) => {
          const g = by.get(name)
          const c = statusClass(g, attempt?.soft_cost ?? 0)
          return (
            <span key={name} style={{ display: 'contents' }}>
              <div className={`gate ${c}`}>
                <Icon name={name} />
                <span className="gn">{name}</span>
                <span className="gv">{g && !g.skipped && g.ok !== null ? cm(g.value_m) : 'idle'}</span>
              </div>
              {i < ORDER.length - 1 && <span className="chev">›</span>}
            </span>
          )
        })}
      </div>
      <div className={`commitcell${attempt?.committed ? ' ready' : ''}`}>
        <Icon name="commit" /><span className="label">commit</span>
      </div>
    </div>
  )
}
