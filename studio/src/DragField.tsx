import { useRef, useState, type ReactNode } from 'react'

// A working Gaea-style numeric field: a recessed bar with a teal fill, scrubbed by
// dragging horizontally; a plain click (no drag) drops into a typed input. An
// optional prefix (e.g. an axis letter) sits at the left of the field.
export function DragField({ value, onChange, min = -2, max = 2, step = 0.01, decimals = 2, unit, prefix, showFill = true }: {
  value: number
  onChange: (v: number) => void
  min?: number
  max?: number
  step?: number
  decimals?: number
  unit?: string
  prefix?: ReactNode
  showFill?: boolean   // the Gaea-style teal fill bar (off for unbounded values like CoM axes)
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
      className={`dragfield${prefix != null ? ' has-prefix' : ''}`} title="drag to scrub · click to type"
      onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp}
    >
      {showFill && <span className="fill" style={{ width: `${pct}%` }} />}
      {prefix != null && <span className="dprefix">{prefix}</span>}
      <span className="dv">{value.toFixed(decimals)}</span>
      {unit && <span className="du">{unit}</span>}
    </div>
  )
}
