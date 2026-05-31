import { Icon } from './Icons'
import { DragField } from './DragField'
import type { Verdict } from './api'

export function Inspector({ pos, setPos, verdict, busy, sweptDeg, onSweptDeg, onValidate, onRepair, onCommit }: {
  pos: number[]
  setPos: (p: number[]) => void
  verdict: Verdict | null
  busy: boolean
  sweptDeg?: number
  onSweptDeg?: (deg: number) => void
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
          <div className="insp-field" key={ax}>
            <span>{ax}</span>
            <DragField value={pos[i]} onChange={(v) => set(i, v)} />
          </div>
        ))}
      </div>

      {verdict && (
        <div className="insp-readout" style={{ color: failed ? 'var(--fail)' : 'var(--pass)' }}>
          {stab && stab.value_m !== null
            ? `stability ${stab.ok ? '✓' : '✗'} ${stab.value_m >= 0 ? '+' : '−'}${Math.abs(stab.value_m * 100).toFixed(1)}cm`
            : verdict.ok ? 'all gates pass' : `stopped at ${verdict.stopped_at}`}
        </div>
      )}

      {onSweptDeg && (
        <div style={{ marginTop: 12 }}>
          <div className="label" style={{ marginBottom: 6 }}>
            Articulation · door swing <span style={{ color: 'var(--ink4)' }}>{sweptDeg ? `${sweptDeg}°` : 'off'}</span>
          </div>
          <input
            type="range" min={0} max={180} step={5} value={sweptDeg ?? 0}
            disabled={busy} style={{ width: '100%', accentColor: 'var(--soft)' }}
            onChange={(e) => onSweptDeg(parseInt(e.target.value, 10))}
          />
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
