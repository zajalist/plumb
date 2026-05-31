import { render, screen, fireEvent } from '@testing-library/react'
import { Splash } from './Splash'

test('renders brand + actions and fires New / Open-recent (no LED dots)', () => {
  const onNew = vi.fn(), onOpen = vi.fn(), onOpenRecent = vi.fn()
  const recent = [{ name: 'kitchen.wdf', at: Date.now() - 120_000 }]
  const { container } = render(
    <Splash recent={recent} onNew={onNew} onOpen={onOpen} onOpenRecent={onOpenRecent} />,
  )

  expect(screen.getByText('Plumb')).toBeInTheDocument()

  fireEvent.click(screen.getByText('New project'))
  expect(onNew).toHaveBeenCalledTimes(1)

  fireEvent.click(screen.getByText('kitchen.wdf'))
  expect(onOpenRecent).toHaveBeenCalledWith(recent[0])

  // austere guarantee: no glowing status dots
  expect(container.querySelector('.dot')).toBeNull()
})

test('shows the empty recent state when there is nothing recent', () => {
  render(<Splash recent={[]} onNew={() => {}} onOpen={() => {}} onOpenRecent={() => {}} />)
  expect(screen.getByText(/no recent projects/i)).toBeInTheDocument()
})
