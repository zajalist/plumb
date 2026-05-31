import { render, screen } from '@testing-library/react'
import { Properties } from './Properties'
import type { PAP } from './api'

const PAP_FIX: PAP = {
  asset_id: 'bronze_figure', profile: 'rigid_prop',
  geometry: { obb: [0.15, 0.15, 0.75], volume_m3: 0.031, convex_parts: 9, watertight: true },
  semantics: {
    cls: 'statue', up: [0, 0, 1], front: [0, 1, 0],
    materials: [{ part: 'body', mat: 'bronze', conf: 0.82 }, { part: 'base', mat: 'stone', conf: 0.74 }],
    conf: 0.8,
  },
  physical: { mass_kg: 48.0, com: [0, 0.04, 0.71], inertia: [], hollow: false, conf: 0.7 },
  structural: { support_footprint: [], max_load_kg_est: null, experimental: true },
  rest_states: ['upright'],
}

test('renders the real baked numbers from a PAP', () => {
  render(<Properties pap={PAP_FIX} />)
  expect(screen.getByText('48.0 kg')).toBeInTheDocument()
  expect(screen.getByText('statue')).toBeInTheDocument()
  expect(screen.getByText('yes · 9 parts')).toBeInTheDocument()
  expect(screen.getByText(/bronze/)).toBeInTheDocument()
})

test('shows an empty state when no asset is selected', () => {
  render(<Properties pap={null} />)
  expect(screen.getByText(/Import or select an asset/i)).toBeInTheDocument()
})
