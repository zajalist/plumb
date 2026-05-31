// Recent .wdf projects, persisted in localStorage. A browser app has no real
// filesystem paths, so an entry is just the project name + when it was last
// opened. WP-3 (.wdf project I/O) will attach real content; this only tracks.
export type RecentEntry = { name: string; at: number }

const KEY = 'plumb.recent'
const MAX = 6

export function getRecent(): RecentEntry[] {
  try {
    const list = JSON.parse(localStorage.getItem(KEY) ?? '[]')
    if (!Array.isArray(list)) return []
    return list.filter(
      (e): e is RecentEntry => !!e && typeof e.name === 'string' && typeof e.at === 'number',
    )
  } catch {
    return []
  }
}

export function addRecent(name: string): RecentEntry[] {
  const next = [{ name, at: Date.now() }, ...getRecent().filter((e) => e.name !== name)].slice(0, MAX)
  try { localStorage.setItem(KEY, JSON.stringify(next)) } catch { /* quota / disabled */ }
  return next
}

export function clearRecent(): void {
  try { localStorage.removeItem(KEY) } catch { /* ignore */ }
}

export function formatAgo(at: number, now = Date.now()): string {
  const s = Math.max(0, Math.floor((now - at) / 1000))
  if (s < 60) return 'just now'
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}
