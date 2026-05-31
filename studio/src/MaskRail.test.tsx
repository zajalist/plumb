import { render, screen, fireEvent } from '@testing-library/react'
import { vi } from 'vitest'
import { IconDefs } from './Icons'
import { MaskRail } from './MaskRail'
import type { MaskProviderMeta } from './masks'

const CATALOG: MaskProviderMeta[] = [
  { key: 'materials', name: 'Materials', source: 'geometry', category: 'material', archetype: 'categorical', role: 'surface', needs_images: false, available: true },
  { key: 'saliency', name: 'Saliency', source: 'hf', category: 'artistic', archetype: 'scalar', role: 'surface', needs_images: true, available: false },
  { key: 'gravity_field', name: 'Gravity / force', source: 'geometry', category: 'physics', archetype: 'vector', role: 'overlay', needs_images: false, available: true },
]

function setup(over: Partial<Parameters<typeof MaskRail>[0]> = {}) {
  const onSurface = vi.fn(); const onOverlay = vi.fn()
  render(<>
    <IconDefs />
    <MaskRail catalog={CATALOG} masks={[]} surface="textured" overlays={new Set()}
      computing={new Set()} errors={{}} onSurface={onSurface} onOverlay={onOverlay} {...over} />
  </>)
  return { onSurface, onOverlay }
}

test('lists textured + surface providers and overlays', () => {
  setup()
  expect(screen.getByText('textured')).toBeInTheDocument()
  expect(screen.getByText('Materials')).toBeInTheDocument()
  expect(screen.getByText('Saliency')).toBeInTheDocument()
  expect(screen.getByText('Gravity / force')).toBeInTheDocument()
})

test('clicking an available surface provider calls onSurface', () => {
  const { onSurface } = setup()
  fireEvent.click(screen.getByText('Materials'))
  expect(onSurface).toHaveBeenCalledWith('materials')
})

test('an unavailable provider is gated and not clickable', () => {
  const { onSurface } = setup()
  expect(screen.getByText('no hf key')).toBeInTheDocument()
  fireEvent.click(screen.getByText('Saliency'))
  expect(onSurface).not.toHaveBeenCalled()
})

test('toggling an overlay calls onOverlay', () => {
  const { onOverlay } = setup()
  fireEvent.click(screen.getByText('Gravity / force'))
  expect(onOverlay).toHaveBeenCalledWith('gravity_field')
})

test('filter narrows the visible rows', () => {
  setup()
  fireEvent.change(screen.getByPlaceholderText('Filter masks…'), { target: { value: 'gravity' } })
  expect(screen.queryByText('Materials')).not.toBeInTheDocument()
  expect(screen.getByText('Gravity / force')).toBeInTheDocument()
})
