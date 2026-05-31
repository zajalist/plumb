import { Icon } from './Icons'
import { formatAgo, type RecentEntry } from './recent'

// The pre-IDE launch screen: brand moment, then New / Open / Recent. Austere,
// on-brand, fast. No physics here — it only routes into the IDE.
export function Splash({ recent, onNew, onOpen, onOpenRecent }: {
  recent: RecentEntry[]
  onNew: () => void
  onOpen: (file: File) => void
  onOpenRecent: (entry: RecentEntry) => void
}) {
  return (
    <div className="splash">
      <div className="splash-stage">
        <span className="crop tl" /><span className="crop tr" />
        <span className="crop bl" /><span className="crop br" />

        <div className="splash-hero">
          <img className="splash-mark" src="/logo.svg" alt="Plumb" />
          <div className="splash-word">Plumb</div>
          <div className="splash-tag">spatial validation for physical worlds</div>
        </div>

        <div className="splash-actions">
          <button className="splash-action" onClick={onNew}>
            <Icon name="new" />
            <span className="sa-l">New project</span>
            <span className="sa-k mono">.wdf</span>
          </button>
          <label className="splash-action">
            <Icon name="open" />
            <span className="sa-l">Open .wdf…</span>
            <span className="sa-k mono">browse</span>
            <input type="file" accept=".wdf" style={{ display: 'none' }}
              onChange={(e) => { const f = e.target.files?.[0]; if (f) onOpen(f) }} />
          </label>
        </div>

        <div className="splash-recent">
          <div className="label">Recent</div>
          {recent.length === 0 ? (
            <div className="splash-empty">No recent projects</div>
          ) : (
            <ul>
              {recent.map((e) => (
                <li key={e.name}>
                  <button onClick={() => onOpenRecent(e)}>
                    <Icon name="open" />
                    <span className="rname">{e.name}</span>
                    <span className="rtime">{formatAgo(e.at)}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div className="splash-foot mono">v0.1 · local cortex</div>
    </div>
  )
}
