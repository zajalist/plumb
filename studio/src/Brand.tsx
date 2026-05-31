// The real PLUMB mark (the inlined #logo aperture) + wordmark.
export function Brand() {
  return (
    <div className="brand">
      <svg width="26" height="24" aria-label="PLUMB"><use href="#logo" /></svg>
      <span className="word">PLUMB</span>
    </div>
  )
}
