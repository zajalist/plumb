import { GateIcon3D, type GateShape } from './GateIcon3D'
import { DragField } from './DragField'

// Loose shape so this accepts both the live contract Verdict and the demo fixture.
type GateLike = { gate: string; ok: boolean | null; skipped: boolean; value_m: number | null }
type VerdictLike = { gates: GateLike[]; soft_cost: number; committed?: boolean; ok?: boolean; stopped_at?: string | null } | null

const ORDER = ['collision', 'stability', 'constraints', 'reach'] as const
const AXIS = ['#E0694F', '#6FBF73', '#5C8BD6']   // X red · Y green · Z blue

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

// The gate-stack toolbar: live 3D gate icons on the left, then a UE4-style transform
// block (Location / Rotation) and the validate → repair → commit action cluster on
// the right. Rotation feeds the quaternion, so it affects the stability gate.
export function GateStack({ verdict, pos, setPos, rot, setRot, busy, onValidate, onRepair, onCommit, freeStanding, setFreeStanding }: {
  verdict: VerdictLike
  pos?: number[]
  setPos?: (p: number[]) => void
  rot?: number[]
  setRot?: (r: number[]) => void
  busy?: boolean
  onValidate?: () => void
  onRepair?: () => void
  onCommit?: () => void
  freeStanding?: boolean
  setFreeStanding?: (b: boolean) => void
}) {
  const by = new Map((verdict?.gates ?? []).map((g) => [g.gate, g]))
  const stab = by.get('stability')
  const failed = verdict ? !verdict.ok : false
  const ready = !!verdict?.ok
  const hasXform = !!(pos && setPos && rot && setRot && onValidate)
  const setP = (i: number, v: number) => { const p = [...(pos ?? [0, 0, 0])]; p[i] = v; setPos?.(p) }
  const setR = (i: number, v: number) => { const r = [...(rot ?? [0, 0, 0])]; r[i] = v; setRot?.(r) }

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

      {hasXform && (
        <div className="gact">
          <div className="gx">
            <div className="gx-row">
              <span className="gx-lbl">Loc</span>
              {['X', 'Y', 'Z'].map((_, i) => (
                <DragField key={i} value={pos![i]} min={-2} max={2} step={0.01} decimals={2} showFill={false}
                  prefix={<span style={{ color: AXIS[i], fontWeight: 700 }}>{'XYZ'[i]}</span>}
                  onChange={(v) => setP(i, v)} />
              ))}
            </div>
            <div className="gx-row">
              <span className="gx-lbl">Rot</span>
              {['X', 'Y', 'Z'].map((_, i) => (
                <DragField key={i} value={rot![i]} min={-180} max={180} step={1} decimals={0} unit="°" showFill={false}
                  prefix={<span style={{ color: AXIS[i], fontWeight: 700 }}>{'XYZ'[i]}</span>}
                  onChange={(v) => setR(i, v)} />
              ))}
            </div>
          </div>

          <div className="gact-sep" />

          <div className="gact-r">
            {setFreeStanding && (
              <div className="gsupport" title="Free-standing: the base co-moves with the body, so lateral placement doesn't topple it. Pedestal: the base is anchored at the origin (the gallery model).">
                <span className="gsupport-lbl">Support</span>
                <button
                  className={`gsupport-opt ${freeStanding ? 'on' : ''}`}
                  onClick={() => setFreeStanding(true)}
                >Free-standing</button>
                <button
                  className={`gsupport-opt ${!freeStanding ? 'on' : ''}`}
                  onClick={() => setFreeStanding(false)}
                >Pedestal</button>
              </div>
            )}
            <div className={`gact-read ${failed ? 'fail' : ready ? 'pass' : ''}`}>
              {verdict
                ? stab && stab.value_m !== null
                  ? `${stab.ok ? 'Stable' : 'Unstable'} · ${cm(stab.value_m)}`
                  : ready ? 'All gates pass' : `Stopped at ${verdict.stopped_at ?? 'gate'}`
                : 'Not validated'}
            </div>
            <div className="gact-btns">
              <button className="tbtn primary" disabled={busy} onClick={onValidate}>Validate</button>
              <button className="tbtn warn" disabled={busy || !failed} onClick={onRepair}>Repair</button>
              <button className="tbtn go" disabled={busy || !ready} onClick={onCommit}>Commit</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
