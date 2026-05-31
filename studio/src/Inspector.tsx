// Door articulation control (WP-6). Placement (pos/validate/repair/commit) lives in the
// GateStack now, so this slim Inspector is just the door-swing angle → real /swept wedge
// in the viewport. Rendered as the Properties panel footer.
export function Inspector({ sweptDeg, onSweptDeg, busy }: {
  sweptDeg?: number
  onSweptDeg?: (deg: number) => void
  busy?: boolean
}) {
  if (!onSweptDeg) return null
  return (
    <div className="psec insp" style={{ borderBottom: 'none', borderTop: '1px solid var(--line)' }}>
      <div className="label" style={{ marginBottom: 6 }}>
        Articulation · door swing <span style={{ color: 'var(--ink4)' }}>{sweptDeg ? `${sweptDeg}°` : 'off'}</span>
      </div>
      <input
        type="range" min={0} max={180} step={5} value={sweptDeg ?? 0}
        disabled={busy} style={{ width: '100%', accentColor: 'var(--soft)' }}
        onChange={(e) => onSweptDeg(parseInt(e.target.value, 10))}
      />
    </div>
  )
}
