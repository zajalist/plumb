/**
 * Visual design tokens — the single source for status/port colours and labels.
 *
 * Previously duplicated across ConstraintGraph.tsx and Inspector.tsx (and inline in
 * App.tsx / App.css). One palette, imported everywhere, so the canvas and inspector
 * can never drift.
 */
import type { GateStatus, PortType } from './engine'

// Graphite-glass PLUMB palette (matches theme.css gate semantics): teal/terracotta/
// amber — the only saturated colors in the studio. No neon.
export const STATUS_COLOR: Record<GateStatus, string> = {
  pass: '#34C0AD', // teal
  fail: '#E0694F', // terracotta
  soft: '#D9A84C', // amber
  idle: '#474E54', // ink4
}

export const STATUS_LABEL: Record<GateStatus, string> = {
  pass: 'PASS',
  fail: 'FAIL',
  soft: 'SOFT',
  idle: 'IDLE',
}

// Typed-port colours — desaturated, cool; distinct but never loud (spec §9.2).
export const PORT_COLOR: Record<PortType, string> = {
  object: '#34C0AD', // teal (the noun)
  scalar: '#6E8BA0', // steel (a number)
  bool: '#A088B0', // muted violet (a gate)
  verdict: '#D9A84C', // amber (the commit)
}

export const KIND_LABEL: Record<string, string> = {
  asset: 'Asset · noun',
  measure: 'Measure',
  law: 'Law',
  field: 'Field · context',
  verdict: 'Verdict',
}
