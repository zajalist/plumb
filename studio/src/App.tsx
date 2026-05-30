import { useCallback, useRef, useState } from 'react'
import { ReactFlowProvider } from '@xyflow/react'
import RerunViewer, { type ViewerControls } from './components/RerunViewer'
import ConstraintGraph from './components/ConstraintGraph'
import Palette from './components/Palette'
import { stabilityMargin, stableStatus, type SceneState } from './lib/engine'
import { STATUS_COLOR } from './lib/theme'
import './App.css'

// The two demo beats — each pins the bronze x-offset and the viewer keyframe.
const BEATS = [
  { label: '① placed by vibes', x: 0.0, frac: 0 },
  { label: '② repaired +6cm ✓', x: 0.06, frac: 1 },
]
const BRONZE_X_SAFE = 0.06 // maps the continuous knob onto the viewer's 0..1 range

export default function App() {
  const [scene, setScene] = useState<SceneState>({ bronzeX: 0 })
  const [bottomH, setBottomH] = useState(360)
  const controls = useRef<ViewerControls | null>(null)

  // Drag the handle to resize the node-editor block (the 3D viewer takes the rest).
  // Uses pointer capture so moves are routed to the handle even when the cursor
  // passes over the Rerun canvas — otherwise the canvas swallows the events and
  // the handle can only ever move one way.
  const startResize = useCallback((e: React.PointerEvent) => {
    e.preventDefault()
    const handle = e.currentTarget as HTMLElement
    handle.setPointerCapture(e.pointerId)
    const onMove = (ev: PointerEvent) => {
      const h = window.innerHeight - ev.clientY
      setBottomH(Math.min(window.innerHeight - 160, Math.max(180, h)))
    }
    const onUp = (ev: PointerEvent) => {
      handle.releasePointerCapture(ev.pointerId)
      handle.removeEventListener('pointermove', onMove)
      handle.removeEventListener('pointerup', onUp)
      document.body.style.userSelect = ''
    }
    document.body.style.userSelect = 'none'
    handle.addEventListener('pointermove', onMove)
    handle.addEventListener('pointerup', onUp)
  }, [])

  // The knob (slider) drives the live graph; nudge the 3D viewer toward the
  // nearest keyframe so the scene roughly follows (JS API can't set transforms).
  const setBronzeX = useCallback((x: number) => {
    setScene({ bronzeX: x })
    controls.current?.seekFraction(Math.min(1, x / BRONZE_X_SAFE))
  }, [])

  // A beat button pins both the knob and the viewer keyframe.
  const goToBeat = useCallback((i: number) => {
    const beat = BEATS[i]
    setScene({ bronzeX: beat.x })
    controls.current?.seekFraction(beat.frac)
  }, [])

  // Live verdict badge from the stability margin (the bet). Same rule the
  // `stable` law uses — `stableStatus` is the single source.
  const margin = stabilityMargin(scene.bronzeX)
  const badge =
    stableStatus(margin) === 'pass'
      ? { text: 'ALL GREEN', color: STATUS_COLOR.pass }
      : { text: 'STOPPED · STABILITY', color: STATUS_COLOR.fail }
  const activeBeat = scene.bronzeX < (BEATS[0].x + BEATS[1].x) / 2 ? 0 : 1

  return (
    <div className="app" style={{ gridTemplateRows: `44px 1fr ${bottomH}px` }}>
      <header className="topbar">
        <div className="brand">
          PLUMB<span className="brand-dim"> · spatial conscience</span>
        </div>
        <div className="verdict" style={{ color: badge.color }}>
          <span className="dot" style={{ background: badge.color }} />
          {badge.text}
          <span className="verdict-num">margin {margin >= 0 ? '+' : ''}{(margin * 100).toFixed(1)}cm</span>
        </div>
      </header>

      <div className="viewer-pane">
        <RerunViewer rrd="/gallery.rrd" onReady={(c) => (controls.current = c)} />
      </div>

      <div className="bottom">
        <div
          className="resize-handle"
          onPointerDown={startResize}
          role="separator"
          aria-orientation="horizontal"
          title="Drag to resize the node editor"
        />
        <div className="scrubber">
        <span className="scrubber-label">beat</span>
        <div className="steps">
          {BEATS.map((b, i) => (
            <button
              key={b.label}
              className={`step ${i === activeBeat ? 'active' : ''}`}
              style={{ '--c': i === 0 ? STATUS_COLOR.fail : STATUS_COLOR.pass } as React.CSSProperties}
              onClick={() => goToBeat(i)}
            >
              {b.label}
            </button>
          ))}
        </div>
        <span className="scrubber-hint">…or drag the bronze_figure knob for the in-between</span>
      </div>

        <div className="graph-pane">
          <ReactFlowProvider>
            <Palette />
            <ConstraintGraph scene={scene} setBronzeX={setBronzeX} />
          </ReactFlowProvider>
        </div>
      </div>
    </div>
  )
}
