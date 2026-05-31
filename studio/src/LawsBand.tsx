import { Icon } from './Icons'
import type { WdfScene } from './api'

// The constraints declared by an opened .wdf scene, as an austere band: the scene
// name + environment fields, then each law as a chip (sage = hard, ochre = soft).
export function LawsBand({ scene }: { scene: WdfScene }) {
  return (
    <div className="lawsband">
      <div className="lb-title"><Icon name="constraints" /><span>{scene.name}</span></div>
      <div className="lb-fields">
        {scene.fields.map((f) => (
          <span key={f.key} className="lb-field mono">{f.key}: {f.value}</span>
        ))}
      </div>
      <div className="lb-laws">
        {scene.laws.map((l) => (
          <span key={l.name} className={`lb-law ${l.hard ? 'hard' : 'soft'}`} title={l.expr}>
            {l.name}<em>{l.hard ? 'hard' : 'soft'}</em>
          </span>
        ))}
      </div>
    </div>
  )
}
