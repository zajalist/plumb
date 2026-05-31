import { useEffect, useRef } from 'react'
import { WebViewer } from '@rerun-io/web-viewer'

/** A handle the parent uses to drive the viewer's time cursor from outside. */
export type ViewerControls = {
  /** Jump the time cursor to a normalized position (0 = first frame, 1 = last). */
  seekFraction: (t: number) => void
}

type Props = {
  /** URL of the .rrd to load (served from /public). */
  rrd: string
  /** Called once the recording is open and we know its id/timeline/range. */
  onReady?: (controls: ViewerControls) => void
  /** Called whenever the viewer's time cursor moves (normalized 0..1). */
  onTimeFraction?: (t: number) => void
}

// Panels we strip so only the 3D scene remains — this is the "fork-lite" move:
// we keep Rerun's 3D guts and hide its chrome instead of rebuilding the viewer.
const HIDDEN_PANELS = ['top', 'blueprint', 'selection', 'time'] as const

/**
 * Embeds Rerun's web viewer (Rust compiled to Wasm) as a bare 3D canvas.
 *
 * We use the core `@rerun-io/web-viewer` class rather than the React wrapper
 * because only the core exposes `override_panel_state` (to hide chrome) and the
 * time-control methods (`set_current_time`) we need to sync with the node graph.
 */
export default function RerunViewer({ rrd, onReady, onTimeFraction }: Props) {
  const parentRef = useRef<HTMLDivElement>(null)
  const viewerRef = useRef<WebViewer | null>(null)

  useEffect(() => {
    if (!parentRef.current) return

    const viewer = new WebViewer()
    viewerRef.current = viewer
    let disposed = false
    const offFns: Array<() => void> = []

    // Track the active recording/timeline so we can read & set time later.
    let recordingId: string | null = null
    let timeline: string | null = null
    let range: { min: number; max: number } | null = null

    const refreshContext = () => {
      recordingId = viewer.get_active_recording_id()
      if (!recordingId) return false
      timeline = viewer.get_active_timeline(recordingId)
      if (!timeline) return false
      range = viewer.get_time_range(recordingId, timeline)
      return !!range
    }

    viewer
      .start(rrd, parentRef.current, {
        hide_welcome_screen: true,
        theme: 'dark', // dark "device" viewport so green/amber/red overlays pop
        width: '100%',
        height: '100%',
      })
      .then(() => {
        if (disposed) return
        for (const p of HIDDEN_PANELS) viewer.override_panel_state(p, 'hidden')

        // When the recording lands we know its id/timeline/range.
        offFns.push(
          viewer.on('recording_open', () => {
            if (refreshContext()) {
              onReady?.({
                seekFraction: (t: number) => {
                  if (!recordingId || !timeline || !range) return
                  const clamped = Math.min(1, Math.max(0, t))
                  const time = range.min + (range.max - range.min) * clamped
                  viewer.set_current_time(recordingId, timeline, time)
                },
              })
            }
          }),
        )

        // Mirror the viewer's cursor back out as a normalized fraction.
        offFns.push(
          viewer.on('time_update', (e) => {
            if (!range) refreshContext()
            if (!range) return
            const span = range.max - range.min
            const frac = span > 0 ? (e.time - range.min) / span : 0
            onTimeFraction?.(Math.min(1, Math.max(0, frac)))
          }),
        )
      })
      .catch((err) => console.error('Rerun viewer failed to start:', err))

    return () => {
      disposed = true
      for (const off of offFns) off()
      viewer.stop()
      viewerRef.current = null
    }
    // We intentionally start the viewer once; rrd is static for the demo.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rrd])

  return <div ref={parentRef} style={{ width: '100%', height: '100%' }} />
}
