import { useCallback, useRef, useState } from 'react'
import RerunViewer, { type ViewerControls } from './RerunViewer'
import ConstraintGraph from './ConstraintGraph'
import { attempts } from './verdicts'
import './App.css'

const N = attempts.length

export default function App() {
  const [idx, setIdx] = useState(0)
  const controls = useRef<ViewerControls | null>(null)

  const attempt = attempts[idx]

  // Scrubber → viewer: move the 3D time cursor to this attempt's keyframe.
  const goTo = useCallback((next: number) => {
    const clamped = Math.min(N - 1, Math.max(0, next))
    setIdx(clamped)
    controls.current?.seekFraction(N > 1 ? clamped / (N - 1) : 0)
  }, [])

  // Viewer → scrubber: if the user plays the recording, reflect the attempt.
  const onTimeFraction = useCallback((frac: number) => {
    const nearest = Math.round(frac * (N - 1))
    setIdx((cur) => (cur === nearest ? cur : nearest))
  }, [])

  const verdictBadge = attempt.ok
    ? { text: 'ALL GREEN', color: '#28c850' }
    : { text: `STOPPED · ${attempt.stopped_at?.toUpperCase()}`, color: '#dc3232' }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          PLUMB<span className="brand-dim"> · spatial conscience</span>
        </div>
        <div className="verdict" style={{ color: verdictBadge.color }}>
          <span className="dot" style={{ background: verdictBadge.color }} />
          {verdictBadge.text}
        </div>
      </header>

      <div className="viewer-pane">
        <RerunViewer
          rrd="/gallery.rrd"
          onReady={(c) => (controls.current = c)}
          onTimeFraction={onTimeFraction}
        />
      </div>

      <div className="scrubber">
        <button onClick={() => goTo(idx - 1)} disabled={idx === 0}>
          ◀ prev
        </button>
        <div className="steps">
          {attempts.map((a, i) => (
            <button
              key={a.attempt}
              className={`step ${i === idx ? 'active' : ''}`}
              style={{ '--c': a.ok ? '#28c850' : '#dc3232' } as React.CSSProperties}
              onClick={() => goTo(i)}
            >
              attempt {i + 1}
              {a.committed ? ' ✓' : ''}
            </button>
          ))}
        </div>
        <button onClick={() => goTo(idx + 1)} disabled={idx === N - 1}>
          next ▶
        </button>
      </div>

      <div className="graph-pane">
        <ConstraintGraph attempt={attempt} />
      </div>
    </div>
  )
}
