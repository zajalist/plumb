/**
 * Visual design tokens — the single source for status/port colours and labels.
 *
 * Previously duplicated across ConstraintGraph.tsx and Inspector.tsx (and inline in
 * App.tsx / App.css). One palette, imported everywhere, so the canvas and inspector
 * can never drift.
 */
import type { GateStatus, PortType } from './engine'

export const STATUS_COLOR: Record<GateStatus, string> = {
  pass: '#28c850',
  fail: '#dc3232',
  soft: '#ebaa00',
  idle: '#5a5f66',
}

export const STATUS_LABEL: Record<GateStatus, string> = {
  pass: 'PASS',
  fail: 'FAIL',
  soft: 'SOFT',
  idle: 'IDLE',
}

// Typed-port colours (spec §9.2): object → gold, scalar → blue, bool → purple, verdict → green.
export const PORT_COLOR: Record<PortType, string> = {
  object: '#c9a227',
  scalar: '#4a9eff',
  bool: '#b06cff',
  verdict: '#28c850',
}

export const KIND_LABEL: Record<string, string> = {
  asset: 'Asset · noun',
  measure: 'Measure',
  law: 'Law',
  field: 'Field · context',
  verdict: 'Verdict',
}
