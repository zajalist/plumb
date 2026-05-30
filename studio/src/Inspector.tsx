import { Icon } from './Icons'
import type { Verdict } from './api'

export function Inspector({ pos, setPos, verdict, busy, onValidate, onRepair, onCommit }: {
  pos: number[]
  setPos: (p: number[]) => void
  verdict: Verdict | null
  busy: boolean
  onValidate: () => void
  onRepair: () => void
  onCommit: () => void
}) {
  const stab = verdict?.gates.find((g) => g.gate === 'stability')
  const failed = verdict ? !verdict.ok : false
  const set = (i: number, v: number) => { const p = [...pos]; p[i] = v; setPos(p) }
  const AXES = ['X', 'Y', 'Z']
  return (
    <div className="psec insp" style={{ borderBottom: 'none', borderTop: '1px solid var(--line)' }}>
      <div className="label" style={{ marginBottom: 8 }}>Placement</div>
      <div className="insp-grid">
        {AXES.map((ax, i) => (
          <label className="insp-field" key={ax}>
            <span>{ax}</span>
            <input
              type="number" step="0.01" value={pos[i]}
              onChange={(e) => set(i, parseFloat(e.target.value) || 0)}
            />
          </label>
        ))}
      </div>

      {verdict && (
        <div className="insp-readout" style={{ color: failed ? 'var(--fail)' : 'var(--pass)' }}>
          {stab && stab.value_m !== null
            ? `stability ${stab.ok ? '✓' : '✗'} ${stab.value_m >= 0 ? '+' : '−'}${Math.abs(stab.value_m * 100).toFixed(1)}cm`
            : verdict.ok ? 'all gates pass' : `stopped at ${verdict.stopped_at}`}
        </div>
      )}

      <div className="insp-btns">
        <button className="ibtn primary" disabled={busy} onClick={onValidate}>
          <Icon name="grid" />Validate
        </button>
        <button className="ibtn sage" disabled={busy || !failed} onClick={onRepair}>
          <Icon name="stability" />Repair
        </button>
        <button className="ibtn" disabled={busy || !verdict?.ok} onClick={onCommit}>
          <Icon name="commit" />Commit
        </button>
      </div>
    </div>
  )
}
