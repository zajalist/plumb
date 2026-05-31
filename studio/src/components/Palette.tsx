import { CATALOG, type NodeDef } from '../lib/catalog'

/**
 * The asset / node library. Drag an item onto the canvas to add it; the canvas
 * reads the op from `dataTransfer` in its `onDrop` and instantiates the node.
 */
export default function Palette() {
  const onDragStart = (e: React.DragEvent, spec: NodeDef) => {
    e.dataTransfer.setData('application/plumb-node', spec.op)
    e.dataTransfer.effectAllowed = 'move'
  }

  return (
    <aside className="palette">
      <div className="palette-head">Library</div>
      <div className="palette-hint">drag onto the canvas</div>
      {CATALOG.map((cat) => (
        <div className="palette-cat" key={cat.title}>
          <div className="palette-cat-head">
            {cat.title}
            <span className="palette-cat-hint">{cat.hint}</span>
          </div>
          {cat.items.map((spec) => (
            <div
              key={spec.op}
              className={`palette-item kind-${spec.kind}`}
              draggable
              onDragStart={(e) => onDragStart(e, spec)}
              title={spec.sub}
            >
              <span className="palette-item-label">{spec.label}</span>
              {spec.sub && <span className="palette-item-sub">{spec.sub}</span>}
            </div>
          ))}
        </div>
      ))}
    </aside>
  )
}
