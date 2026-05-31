/**
 * Visual design tokens — the single source for status/port colours and labels.
 *
 * Previously duplicated across ConstraintGraph.tsx and Inspector.tsx (and inline in
 * App.tsx / App.css). One palette, imported everywhere, so the canvas and inspector
 * can never drift.
 */
import type { GateStatus, PortType } from './engine'

// Austere PLUMB palette (matches theme.css gate semantics): sage/terracotta/ochre,
// muted — the only saturated colors in the studio. No neon.
export const STATUS_COLOR: Record<GateStatus, string> = {
  pass: '#8E9A60', // sage
  fail: '#C16A4A', // terracotta
  soft: '#C2A24E', // ochre
  idle: '#56544A', // ink4
}

export const STATUS_LABEL: Record<GateStatus, string> = {
  pass: 'PASS',
  fail: 'FAIL',
  soft: 'SOFT',
  idle: 'IDLE',
}

// Typed-port colours — desaturated, austere; distinct but never loud (spec §9.2).
export const PORT_COLOR: Record<PortType, string> = {
  object: '#8E9A60', // sage (the noun)
  scalar: '#7E8A9A', // muted slate (a number)
  bool: '#A0879A', // muted mauve (a gate)
  verdict: '#C2A24E', // ochre (the commit)
}

export const KIND_LABEL: Record<string, string> = {
  asset: 'Asset · noun',
  measure: 'Measure',
  law: 'Law',
  field: 'Field · context',
  verdict: 'Verdict',
}
