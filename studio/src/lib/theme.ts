/**
 * Visual design tokens — the single source for status/port colours and labels.
 *
 * Previously duplicated across ConstraintGraph.tsx and Inspector.tsx (and inline in
 * App.tsx / App.css). One palette, imported everywhere, so the canvas and inspector
 * can never drift.
 */
import type { GateStatus, PortType } from './engine'

// Frutiger Aero palette — vibrant, glass-friendly gate semantics.
export const STATUS_COLOR: Record<GateStatus, string> = {
  pass: '#00e5a0', // bright mint
  fail: '#ff4757', // vivid coral
  soft: '#ffba08', // warm gold
  idle: '#3a7098', // slate blue
}

export const STATUS_LABEL: Record<GateStatus, string> = {
  pass: 'PASS',
  fail: 'FAIL',
  soft: 'SOFT',
  idle: 'IDLE',
}

// Typed-port colours — bright, distinct, FA-appropriate.
export const PORT_COLOR: Record<PortType, string> = {
  object:  '#00d4f5', // aqua (the noun)
  scalar:  '#a29bfe', // lavender (a number)
  bool:    '#52e0c4', // mint teal (a gate)
  verdict: '#ffd166', // warm gold (the commit)
}

export const KIND_LABEL: Record<string, string> = {
  asset:   'Asset · noun',
  measure: 'Measure',
  law:     'Law',
  field:   'Field · context',
  verdict: 'Verdict',
}
