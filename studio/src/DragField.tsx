import { useRef, useState } from 'react'

// A working Gaea-style numeric field: a recessed bar with a teal fill, scrubbed by
// dragging horizontally; a plain click (no drag) drops into a typed input. Used for
// the editable placement axes (mass/volume in Properties stay read-only — derived).
export function DragField({ value, onChange, min = -2, max = 2, step = 0.01 }: {
  value: number
  onChange: (v: number) => void
  min?: number
  max?: number
  step?: number
}) {
  const [editing, setEditing] = useState(false)
  const drag = useRef<{ x: number; v: number; moved: boolean } | null>(null)
  const pct = Math.max(0, Math.min(100, ((value - min) / (max - min)) * 100))
  const clamp = (v: number) => Math.max(min, Math.min(max, Math.round(v / step) * step))

  const onPointerDown = (e: React.PointerEvent) => {
    ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
    drag.current = { x: e.clientX, v: value, moved: false }
  }
  const onPointerMove = (e: React.PointerEvent) => {
    if (!drag.current) return
    const dx = e.clientX - drag.current.x
    if (Math.abs(dx) > 2) drag.current.moved = true
    onChange(clamp(drag.current.v + (dx / 150) * (max - min))) // ~150px == full range
  }
  const onPointerUp = (e: React.PointerEvent) => {
    const d = drag.current
    drag.current = null
    ;(e.currentTarget as HTMLElement).releasePointerCapture?.(e.pointerId)
    if (d && !d.moved) setEditing(true) // click without drag → type
  }

  if (editing) {
    return (
      <input
        type="number" step={step} autoFocus defaultValue={value}
        onBlur={(e) => { onChange(clamp(parseFloat(e.target.value) || 0)); setEditing(false) }}
        onKeyDown={(e) => {
          if (e.key === 'Enter') (e.target as HTMLInputElement).blur()
          else if (e.key === 'Escape') setEditing(false)
        }}
      />
    )
  }
  return (
    <div
      className="dragfield" title="drag to scrub · click to type"
      onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp}
    >
      <span className="fill" style={{ width: `${pct}%` }} />
      <span className="dv">{value.toFixed(2)}</span>
    </div>
  )
}
