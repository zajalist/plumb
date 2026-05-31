import { render, screen } from '@testing-library/react'
import { GateStack } from './GateStack'
import type { Verdict } from './api'

const TOPPLE: Verdict = {
  ok: false, stopped_at: 'stability', soft_cost: 0,
  gates: [
    { gate: 'collision', ok: true, skipped: false, value_m: 0.04, fix: null, viz: null, detail: null },
    { gate: 'stability', ok: false, skipped: false, value_m: -0.07, fix: null, viz: null, detail: null },
    { gate: 'constraints', ok: null, skipped: true, value_m: null, fix: null, viz: null, detail: null },
    { gate: 'reach', ok: null, skipped: true, value_m: null, fix: null, viz: null, detail: null },
  ],
}

test('renders a failing stability gate (flat, no dot/LED markup)', () => {
  const { container } = render(<GateStack verdict={TOPPLE} />)
  expect(screen.getByText('stability')).toBeInTheDocument()
  expect(screen.getByText('−7.0 cm')).toBeInTheDocument()
  expect(container.querySelector('.gate.fail')).toBeTruthy()
  // austere guarantee: no glowing status dots
  expect(container.querySelector('.dot')).toBeNull()
})

test('all gates idle when there is no verdict', () => {
  const { container } = render(<GateStack verdict={null} />)
  expect(container.querySelectorAll('.gate.idle').length).toBe(4)
  expect(container.querySelector('.gate.fail')).toBeNull()
})
