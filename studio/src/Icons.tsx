// PLUMB Studio — custom icon language + the real logo.
// Each glyph encodes its concept (built from the aperture geometry); NO icon
// libraries, NO emoji. Raw SVG is injected so the exact paths/attrs survive.

const DEFS = `
<defs>
  <symbol id="logo" viewBox="0 0 565 514">
    <path fill="#586040" d="M360.904 11.2099C365.244 6.87043 369.958 3.13398 374.942 0L422.039 0C427.398 0 432.35 2.85899 435.029 7.49998L564.732 232.153L540.359 256.527L564.915 281.084L435.029 506.053C432.35 510.694 427.398 513.553 422.039 513.553L375.748 513.553C370.466 510.319 365.478 506.417 360.905 501.845L345.437 486.376L351.829 481.265C358.127 476.229 365.15 472.173 372.66 469.237L389.365 462.706C424.199 449.086 444.947 413.149 439.325 376.173L436.628 358.438C435.909 353.711 435.62 348.936 435.754 344.17C409.71 350.256 381.208 343.148 360.904 322.845L345.437 307.376L351.829 302.265C358.127 297.229 365.149 293.173 372.659 290.237L389.364 283.706C403.749 278.082 415.732 268.651 424.447 256.913C415.732 245.176 403.75 235.744 389.365 230.12L372.66 223.589C365.15 220.653 358.127 216.598 351.829 211.562L345.008 206.107L360.905 190.21C381.203 169.912 409.694 162.803 435.732 168.88C435.65 164.372 435.948 159.858 436.628 155.388L439.324 137.653C444.946 100.677 424.198 64.7395 389.364 51.1201L372.659 44.5889C365.15 41.6527 358.127 37.598 351.829 32.5625L345.007 27.1074L360.904 11.2099ZM270.359 256.527L224.728 210.895L237.899 200.361C239.78 198.858 241.713 197.452 243.688 196.142C232.502 167.459 238.491 133.623 261.655 110.458L282.474 89.6406L224.727 31.8945L237.899 21.3623C267.111 -1.9954 308.607 -1.99653 337.819 21.3603L345.007 27.1074L282.474 89.6406L303.291 110.458C325.084 132.251 331.673 163.49 323.062 190.996C328.226 193.528 333.179 196.649 337.82 200.36L345.008 206.107L294.587 256.527L345.437 307.376L337.818 313.467C333.239 317.128 328.358 320.215 323.27 322.729C331.565 350.07 324.907 380.979 303.292 402.595L282.474 423.413L345.437 486.376L337.819 492.467C308.608 515.823 267.112 515.823 237.9 492.466L224.298 481.59L282.474 423.413L261.656 402.596C238.658 379.597 232.59 346.08 243.451 317.53C241.557 316.265 239.705 314.91 237.899 313.466L224.298 302.59L270.359 256.527ZM24.5869 256.527L0.182605 232.124L129.869 7.49999C132.549 2.85901 137.5 0 142.859 0L190.003 0C194.987 3.13396 199.703 6.86952 204.042 11.209L224.727 31.8945L223.888 32.5664C217.592 37.5996 210.571 41.6517 203.063 44.5869L186.354 51.1201C151.521 64.7394 130.772 100.677 136.395 137.653L139.091 155.388C139.682 159.279 139.983 163.202 139.997 167.127C162.885 164.991 186.517 172.684 204.042 190.209L224.728 210.895L223.888 211.565C217.592 216.599 210.571 220.652 203.064 223.587L186.354 230.12C171.969 235.745 159.986 245.176 151.27 256.914C159.986 268.652 171.97 278.082 186.354 283.706L203.06 290.237C210.569 293.173 217.592 297.229 223.89 302.265L224.298 302.59L204.042 322.846C186.517 340.37 162.883 348.064 139.995 345.928C140.02 350.109 139.722 354.293 139.092 358.438L136.395 376.173C130.772 413.149 151.521 449.087 186.354 462.706L203.061 469.237C210.57 472.173 217.593 476.228 223.891 481.264L224.298 481.59L204.042 501.846C199.47 506.418 194.481 510.319 189.199 513.553L142.859 513.553C137.5 513.553 132.549 510.694 129.869 506.053L0 281.113L24.5869 256.527Z"/>
  </symbol>
  <symbol id="i-new" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M6 3h7l5 5v13H6z"/><path d="M13 3v5h5"/><path d="M12 12v5M9.5 14.5h5"/></symbol>
  <symbol id="i-open" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M3 6h6l2 2.5h10V19H3z"/></symbol>
  <symbol id="i-import" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M4 15v4h16v-4"/><path d="M12 4v10M8 10l4 4 4-4"/></symbol>
  <symbol id="i-aperture" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="12" cy="12" r="8.5"/><path d="M12 12 12 3.5M12 12 19.4 16.2M12 12 4.6 16.2"/></symbol>
  <symbol id="i-stability" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M12 3v11"/><path d="M9.4 14h5.2L12 19z" fill="currentColor" stroke="none"/><path d="M4 21h16"/></symbol>
  <symbol id="i-collision" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="9" cy="12" r="5.5"/><circle cx="15" cy="12" r="5.5"/></symbol>
  <symbol id="i-constraints" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M7 4H4v16h3M17 4h3v16h-3"/><path d="M12 9l3 3-3 3-3-3z"/></symbol>
  <symbol id="i-reach" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M4 18l5-5 4 2 7-9"/><circle cx="4" cy="18" r="1.6" fill="currentColor" stroke="none"/><circle cx="9" cy="13" r="1.6" fill="currentColor" stroke="none"/><circle cx="13" cy="15" r="1.6" fill="currentColor" stroke="none"/><circle cx="20" cy="6" r="1.6" fill="currentColor" stroke="none"/></symbol>
  <symbol id="i-commit" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M19 4v16"/><path d="M4 12h11M11 8l4 4-4 4"/></symbol>
  <symbol id="i-mass" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z"/><circle cx="12" cy="14.5" r="2.2" fill="currentColor" stroke="none"/></symbol>
  <symbol id="i-com" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><rect x="4" y="4" width="16" height="16" rx="1"/><path d="M14 5v14M5 9h14" opacity=".5"/><circle cx="14" cy="9" r="2.1" fill="currentColor" stroke="none"/></symbol>
  <symbol id="i-solid" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="12" cy="12" r="7.5" fill="currentColor" stroke="none"/></symbol>
  <symbol id="i-seal" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M12 3l7 4v6c0 4.4-3 7-7 8-4-1-7-3.6-7-8V7z"/></symbol>
  <symbol id="i-lock" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><rect x="5" y="11" width="14" height="9" rx="1.4"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></symbol>
  <symbol id="i-grid" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M4 9h16M4 15h16M9 4v16M15 4v16"/></symbol>
  <symbol id="i-search" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></symbol>
  <symbol id="i-eye" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6-10-6-10-6z"/><circle cx="12" cy="12" r="2.6"/></symbol>
  <symbol id="i-eye-off" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M4 4l16 16"/><path d="M9.5 5.4A9.6 9.6 0 0 1 12 6c6.5 0 10 6 10 6a16 16 0 0 1-3.2 3.6M6.2 7.8A16 16 0 0 0 2 12s3.5 6 10 6a9.6 9.6 0 0 0 3-.5"/></symbol>
  <symbol id="i-plus" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M12 5v14M5 12h14"/></symbol>
  <symbol id="i-caret" viewBox="0 0 24 24" fill="currentColor" stroke="none"><path d="M6 9l6 6 6-6z"/></symbol>
</defs>`

export function IconDefs() {
  return (
    <svg width="0" height="0" style={{ position: 'absolute' }} aria-hidden dangerouslySetInnerHTML={{ __html: DEFS }} />
  )
}

export function Icon({ name, className }: { name: string; className?: string }) {
  return (
    <svg className={className} aria-hidden>
      <use href={`#i-${name}`} />
    </svg>
  )
}
