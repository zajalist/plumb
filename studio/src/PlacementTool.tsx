import { useCallback, useEffect, useMemo, useState } from 'react'
import { addPlacement, clearPlacements, getPlacements, type PlacementExample } from './api'

// "Placement Distribution" demonstrator. You show PLUMB how an asset sits on a tagged
// surface — slide the ground (sink), lean the object (tilt), pick uneven terrain noise —
// and Capture. Each capture is one example; same-tag examples form a distribution the
// MCP serves to an agent via place_on_surface(asset, tag). A side-view makes the pose
// obvious; no dependency on the big 3D viewport, so it can't collide with it.

type Orientation = 'horizontal' | 'inclined' | 'vertical' | 'terrain'
const ORIENTATIONS: { key: Orientation; label: string }[] = [
  { key: 'horizontal', label: 'Floor' }, { key: 'terrain', label: 'Terrain' },
  { key: 'inclined', label: 'Inclined' }, { key: 'vertical', label: 'Wall' },
]
const TAGS = ['terrain', 'floor', 'table', 'wall', 'cabinet', 'shelf']

function mean(xs: number[]) { return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0 }
function std(xs: number[]) { const m = mean(xs); return xs.length ? Math.sqrt(mean(xs.map((x) => (x - m) ** 2))) : 0 }

export function PlacementTool({ assetId, obb }: { assetId: string; obb?: number[] }) {
  const [open, setOpen] = useState(false)
  const [tag, setTag] = useState('terrain')
  const [orientation, setOrientation] = useState<Orientation>('terrain')
  const [sink, setSink] = useState(12)        // cm the object origin sits BELOW the surface (roots/embed)
  const [tilt, setTilt] = useState(4)         // deg lean off the surface normal
  const yaw = 0
  const [noiseAmp, setNoiseAmp] = useState(8) // cm terrain bump amplitude
  const [seed, setSeed] = useState(1)
  const [examples, setExamples] = useState<PlacementExample[]>([])
  const [tags, setTags] = useState<Record<string, number>>({})
  const [busy, setBusy] = useState(false)

  const refresh = useCallback(async () => {
    const r = await getPlacements(assetId); setExamples(r.examples); setTags(r.tags)
  }, [assetId])
  useEffect(() => { if (open) void refresh() }, [open, refresh])

  // object proportions from the OBB (tallest axis = up). Fallback to a generic upright box.
  const [hUp, hWide] = useMemo(() => {
    const h = (obb && obb.length === 3) ? [...obb].map((v) => Math.abs(v)) : [0.4, 0.5, 1.0]
    const up = Math.max(...h); const wide = Math.max(0.05, Math.min(...h))
    return [up, wide]
  }, [obb])

  const capture = async () => {
    setBusy(true)
    try {
      await addPlacement(assetId, {
        tag, orientation, normal_offset: -sink / 100, tilt_deg: tilt, yaw_deg: yaw,
        lateral: [0, 0], noise: orientation === 'terrain' ? { amp: noiseAmp / 100, freq: 1.5, seed } : null,
      })
      if (orientation === 'terrain') setSeed((s) => s + 1)  // next capture, new bumps
      await refresh()
    } finally { setBusy(false) }
  }

  // current-tag distribution (mirrors the cortex stats so the user sees what the MCP returns)
  const dist = useMemo(() => {
    const ex = examples.filter((e) => e.tag === tag)
    if (!ex.length) return null
    return {
      n: ex.length,
      sinkM: -mean(ex.map((e) => e.normal_offset)) * 100, sinkS: std(ex.map((e) => e.normal_offset)) * 100,
      tiltM: mean(ex.map((e) => e.tilt_deg)), tiltS: std(ex.map((e) => e.tilt_deg)),
    }
  }, [examples, tag])

  // ---- side-view geometry (px) ----
  const W = 300, H = 280, cx = W / 2, surfaceY = 150
  const scale = Math.min(110 / hUp, 70 / hWide)   // fit the object
  const objH = hUp * scale, objW = Math.max(10, hWide * scale)
  const sinkPx = (sink / 100) * scale * (hUp / Math.max(hUp, 1))  // visual sink (roughly to scale)
  const surfPts = useMemo(() => {
    // the surface line: flat / inclined / wavy(terrain), sampled across the width
    const pts: [number, number][] = []
    for (let i = 0; i <= 40; i++) {
      const x = (i / 40) * W
      let y = surfaceY
      if (orientation === 'inclined') y += (x - cx) * Math.tan((tilt * Math.PI) / 180) * 0.6
      else if (orientation === 'terrain') {
        const n = Math.sin((x * 0.045) + seed * 1.7) + 0.5 * Math.sin((x * 0.11) + seed * 3.1)
        y += -n * (noiseAmp / 100) * scale
      }
      pts.push([x, y])
    }
    return pts
  }, [orientation, tilt, seed, noiseAmp, scale])

  // Collapsed state renders only AFTER every hook has run, so the hook order is
  // identical whether the panel is open or not (Rules of Hooks — the surfPts
  // useMemo above must never be skipped on the collapsed render).
  if (!open) {
    return (
      <button className="pt-launch" title="Teach how this asset rests on a surface (sink, tilt, surface tag)"
        onClick={() => setOpen(true)}>
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.7">
          <path d="M3 17h18" /><path d="M12 3v9" /><path d="M8.5 8.5 12 12l3.5-3.5" /><path d="M6 17l2-3M18 17l-2-3" />
        </svg>
        Placement distribution
      </button>
    )
  }

  const surfPath = surfPts.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)} ${y.toFixed(1)}`).join(' ')
  const groundFill = `${surfPath} L${W} ${H} L0 ${H} Z`
  const objYBase = surfaceY + sinkPx  // base sits `sink` below the surface line

  return (
    <div className="pt-scrim" onPointerDown={() => setOpen(false)}>
    <div className="pt-overlay" onPointerDown={(e) => e.stopPropagation()}>
      <div className="pt-head">
        <span className="pt-title">Placement distribution · <span className="mono">{assetId}</span></span>
        <button className="pt-x" onClick={() => setOpen(false)}>✕</button>
      </div>
      <div className="pt-body">
        <div className="pt-view">
          <svg viewBox={`0 0 ${W} ${H}`} width="100%" height="100%">
            <rect x="0" y="0" width={W} height={H} fill="#0b0e10" />
            <path d={groundFill} fill="rgba(217,168,76,.08)" />
            <path d={surfPath} fill="none" stroke="#D9A84C" strokeWidth="2" />
            {/* surface normal */}
            <line x1={cx} y1={surfaceY} x2={cx} y2={surfaceY - 34} stroke="#D9A84C" strokeWidth="1" strokeDasharray="3 3" opacity="0.6" />
            {/* the object (origin at base centre), leaned by tilt about its base */}
            <g transform={`translate(${cx} ${objYBase}) rotate(${orientation === 'vertical' ? 90 : -tilt})`}>
              <rect x={-objW / 2} y={-objH} width={objW} height={objH} rx="3"
                fill="rgba(52,192,173,.18)" stroke="#34C0AD" strokeWidth="1.5" />
              {/* a little canopy hint on top */}
              <circle cx="0" cy={-objH} r={objW * 0.7} fill="rgba(52,192,173,.12)" stroke="rgba(52,192,173,.5)" />
              <circle cx="0" cy="0" r="2.5" fill="#34C0AD" />{/* origin */}
            </g>
            <text x="8" y={H - 8} fill="var(--ink4)" fontSize="9">side view · {ORIENTATIONS.find((o) => o.key === orientation)?.label}</text>
          </svg>
        </div>

        <div className="pt-ctrl">
          <label className="pt-l">Surface tag</label>
          <input className="pt-tag" list="pt-tags" value={tag} onChange={(e) => setTag(e.target.value)} placeholder="terrain…" />
          <datalist id="pt-tags">{TAGS.map((t) => <option key={t} value={t} />)}</datalist>

          <label className="pt-l">Surface type</label>
          <div className="pt-seg">
            {ORIENTATIONS.map((o) => (
              <button key={o.key} className={orientation === o.key ? 'on' : ''} onClick={() => setOrientation(o.key)}>{o.label}</button>
            ))}
          </div>

          <label className="pt-l">Sink <span className="pt-num">{sink} cm</span></label>
          <input type="range" min={-20} max={60} step={1} value={sink} onChange={(e) => setSink(+e.target.value)} />

          <label className="pt-l">Tilt <span className="pt-num">{tilt}°</span></label>
          <input type="range" min={0} max={30} step={1} value={tilt} onChange={(e) => setTilt(+e.target.value)} />

          {orientation === 'terrain' && (
            <>
              <label className="pt-l">Terrain bumps <span className="pt-num">{noiseAmp} cm</span>
                <button className="pt-reroll" onClick={() => setSeed((s) => s + 1)} title="New noise">↻</button></label>
              <input type="range" min={0} max={30} step={1} value={noiseAmp} onChange={(e) => setNoiseAmp(+e.target.value)} />
            </>
          )}

          <button className="pt-cap" disabled={busy} onClick={capture}>{busy ? 'Capturing…' : '+ Capture example'}</button>

          {dist && (
            <div className="pt-dist">
              <div className="pt-dh">“{tag}” distribution · {dist.n} example{dist.n === 1 ? '' : 's'}</div>
              <div className="pt-dr"><span>sink</span><b>{dist.sinkM.toFixed(1)} ± {dist.sinkS.toFixed(1)} cm</b></div>
              <div className="pt-dr"><span>tilt</span><b>{dist.tiltM.toFixed(1)} ± {dist.tiltS.toFixed(1)}°</b></div>
              <div className="pt-mcp mono">place_on_surface("{assetId}", "{tag}")</div>
            </div>
          )}
          {Object.keys(tags).length > 0 && (
            <div className="pt-tags-row">
              {Object.entries(tags).map(([t, n]) => (
                <span key={t} className={`pt-chip${t === tag ? ' on' : ''}`} onClick={() => setTag(t)}>{t} · {n}</span>
              ))}
              <button className="pt-clear" onClick={async () => { await clearPlacements(assetId, tag); await refresh() }}>clear “{tag}”</button>
            </div>
          )}
        </div>
      </div>
    </div>
    </div>
  )
}
