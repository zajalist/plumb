import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

export type SelOption = { value: string; label: string; swatch?: string; group?: string; hint?: string }

// A searchable dropdown (combobox): a compact trigger that opens a type-to-filter
// popover with a grouped, scrollable option list. The popover is portalled to <body>
// with fixed positioning so it is never clipped by a scrollable parent panel. Used for
// the material and bake-profile pickers where the catalog runs to the hundreds.
export function SearchSelect({ value, options, onChange, placeholder = 'Search…', disabled }: {
  value: string
  options: SelOption[]
  onChange: (v: string) => void
  placeholder?: string
  disabled?: boolean
}) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const [rect, setRect] = useState<{ left: number; top: number; width: number } | null>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const popRef = useRef<HTMLDivElement>(null)
  const cur = options.find((o) => o.value === value)

  const place = () => {
    const el = triggerRef.current
    if (!el) return
    const r = el.getBoundingClientRect()
    setRect({ left: r.left, top: r.bottom + 4, width: Math.max(r.width, 220) })
  }
  useLayoutEffect(() => { if (open) place() }, [open])

  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => {
      const t = e.target as Node
      if (!triggerRef.current?.contains(t) && !popRef.current?.contains(t)) setOpen(false)
    }
    const onScroll = () => setOpen(false)
    document.addEventListener('mousedown', onDoc)
    window.addEventListener('resize', onScroll)
    // capture scrolls on any ancestor so the menu doesn't drift away from its trigger
    window.addEventListener('scroll', onScroll, true)
    return () => {
      document.removeEventListener('mousedown', onDoc)
      window.removeEventListener('resize', onScroll)
      window.removeEventListener('scroll', onScroll, true)
    }
  }, [open])

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase()
    const hit = needle
      ? options.filter((o) => o.label.toLowerCase().includes(needle) || o.value.toLowerCase().includes(needle) || (o.group ?? '').toLowerCase().includes(needle))
      : options
    const groups = new Map<string, SelOption[]>()
    for (const o of hit) { const g = o.group ?? ''; if (!groups.has(g)) groups.set(g, []); groups.get(g)!.push(o) }
    return [...groups.entries()]
  }, [q, options])

  return (
    <div className={`ssel${open ? ' open' : ''}`}>
      <button ref={triggerRef} type="button" className="ssel-trigger" disabled={disabled}
        onClick={() => { setOpen((v) => !v); setQ('') }}>
        {cur?.swatch && <span className="ssel-sw" style={{ background: cur.swatch }} />}
        <span className="ssel-cur">{cur?.label ?? value}</span>
        <svg className="ssel-caret" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M6 9l6 6 6-6" /></svg>
      </button>
      {open && rect && createPortal(
        <div ref={popRef} className="ssel-pop" style={{ left: rect.left, top: rect.top, width: rect.width }}
          onPointerDown={(e) => e.stopPropagation()}>
          <input className="ssel-search" autoFocus value={q} placeholder={placeholder}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Escape') setOpen(false) }} />
          <div className="ssel-list">
            {filtered.length === 0 && <div className="ssel-empty">No matches</div>}
            {filtered.map(([group, opts]) => (
              <div key={group || '_'}>
                {group && <div className="ssel-group">{group}</div>}
                {opts.map((o) => (
                  <button key={o.value} type="button" className={`ssel-opt${o.value === value ? ' on' : ''}`}
                    onClick={() => { onChange(o.value); setOpen(false) }}>
                    {o.swatch && <span className="ssel-sw" style={{ background: o.swatch }} />}
                    <span className="ssel-lbl">{o.label}</span>
                    {o.hint && <span className="ssel-hint">{o.hint}</span>}
                  </button>
                ))}
              </div>
            ))}
          </div>
        </div>,
        document.body,
      )}
    </div>
  )
}
