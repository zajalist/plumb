import { ABSTRACT_PALETTE, type AbstractItem } from '../lib/catalog'

/**
 * The node library. Five *abstract* nodes (Object · Measure · Law · Field ·
 * Verdict) — drag one onto the canvas to add it; the specific op (which asset,
 * which measure, …) is then chosen in the inspector (SYNC.md D2). The canvas
 * reads the kind from `dataTransfer` in its `onDrop` and instantiates the node
 * at that kind's default op.
 */
export default function Palette() {
  const onDragStart = (e: React.DragEvent, item: AbstractItem) => {
    e.dataTransfer.setData('application/plumb-node-kind', item.kind)
    e.dataTransfer.effectAllowed = 'move'
  }

  return (
    <aside className="palette">
      <div className="palette-head">Library</div>
      <div className="palette-hint">drag onto the canvas · configure in inspector</div>
      <div className="palette-cat">
        {ABSTRACT_PALETTE.map((item) => (
          <div
            key={item.kind}
            className={`palette-item kind-${item.kind}`}
            draggable
            onDragStart={(e) => onDragStart(e, item)}
            title={item.hint}
          >
            <span className="palette-item-label">{item.label}</span>
            <span className="palette-item-sub">{item.hint}</span>
          </div>
        ))}
      </div>
    </aside>
  )
}
