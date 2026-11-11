import { useId, useRef, useState } from "react";

const NODE_WIDTH = 112;
const NODE_HEIGHT = 42;
const CENTER = { x: 0, y: 0 };

function arrangeNeighbors(graph) {
  const nodes = new Map();
  for (const [direction, neighbors] of [["incoming", graph.callers], ["outgoing", graph.callees]]) {
    for (const node of neighbors) {
      const neighbor = nodes.get(node.id) ?? { ...node };
      neighbor[direction] = true;
      nodes.set(node.id, neighbor);
    }
  }

  const loop = nodes.delete(graph.node.id);
  const count = nodes.size;
  const radius = Math.max(88, count * 16);
  const neighbors = Array.from(nodes.values(), (node, index) => {
    const angle = index * 2 * Math.PI / count - Math.PI / 5;
    return { ...node, x: Math.cos(angle) * radius * 1.65, y: Math.sin(angle) * radius };
  });
  return { loop, neighbors };
}

function edgeEndpoints({ x, y }) {
  const inset = 1 / Math.max(Math.abs(x) / (NODE_WIDTH / 2), Math.abs(y) / (NODE_HEIGHT / 2));
  return `M ${x * inset} ${y * inset} L ${x * (1 - inset)} ${y * (1 - inset)}`;
}

export function CallGraph({ graph, onNavigate, disabled }) {
  const arrowId = useId();
  const [offset, setOffset] = useState(CENTER);
  const [dragging, setDragging] = useState(false);
  const pointer = useRef(null);
  const suppressClick = useRef(false);
  const { loop, neighbors } = arrangeNeighbors(graph);

  function startPan(event) {
    if (!event.isPrimary || event.button !== 0) return;
    suppressClick.current = false;
    if (event.target.closest(".graph-reset")) return;
    pointer.current = {
      id: event.pointerId, x: event.clientX, y: event.clientY, offset, moved: false,
    };
    // Capture on the button when the gesture starts there so a plain click still opens it.
    (event.target.closest("button") ?? event.currentTarget).setPointerCapture(event.pointerId);
  }

  function pan(event) {
    const active = pointer.current;
    if (active?.id !== event.pointerId) return;
    const dx = event.clientX - active.x;
    const dy = event.clientY - active.y;
    if (!active.moved && Math.hypot(dx, dy) < 5) return;
    if (!active.moved) {
      active.moved = true;
      suppressClick.current = true;
      setDragging(true);
    }
    setOffset({ x: active.offset.x + dx, y: active.offset.y + dy });
  }

  function stopPan(event) {
    if (pointer.current?.id !== event.pointerId) return;
    pointer.current = null;
    setDragging(false);
  }

  function handleClick(event) {
    if (suppressClick.current && event.detail > 0) {
      suppressClick.current = false;
      event.stopPropagation();
    }
  }

  function revealFocusedNode(event, node) {
    if (!event.currentTarget.matches(":focus-visible")) return;
    const { clientWidth, clientHeight } = event.currentTarget.closest(".graph-stage");
    const horizontal = Math.max(0, (clientWidth - NODE_WIDTH) / 2 - 8);
    const vertical = Math.max(0, (clientHeight - NODE_HEIGHT) / 2 - 8);
    setOffset(previous => ({
      x: Math.min(horizontal - node.x, Math.max(-horizontal - node.x, previous.x)),
      y: Math.min(vertical - node.y, Math.max(-vertical - node.y, previous.y)),
    }));
  }

  return (
    <div className={`graph-stage${dragging ? " graph-dragging" : ""}`}
      role="group" aria-label="Поле графа вызовов"
      style={{ backgroundPosition: `${offset.x}px ${offset.y}px` }}
      onPointerDown={startPan} onPointerMove={pan} onPointerUp={stopPan}
      onPointerCancel={stopPan} onLostPointerCapture={stopPan} onClickCapture={handleClick}>
      <div className="graph-plane" style={{
        transform: `translate(${offset.x}px, ${offset.y}px)`,
        "--graph-node-width": `${NODE_WIDTH}px`,
        "--graph-node-height": `${NODE_HEIGHT}px`,
      }}>
        <svg viewBox="0 0 1 1" aria-hidden="true">
          <defs>
            <marker id={arrowId} viewBox="0 0 8 8" markerWidth="8" markerHeight="8"
              refX="8" refY="4" orient="auto-start-reverse" markerUnits="userSpaceOnUse">
              <path d="M0 0 L8 4 L0 8 Z" />
            </marker>
          </defs>
          {neighbors.map(node => (
            <path key={node.id} className="graph-edge" d={edgeEndpoints(node)}
              markerStart={node.incoming ? `url(#${arrowId})` : undefined}
              markerEnd={node.outgoing ? `url(#${arrowId})` : undefined} />
          ))}
          {loop && <path className="graph-edge" d="M 20 -21 C 20 -69 79 -62 56 -12" markerEnd={`url(#${arrowId})`} />}
        </svg>
        <div className="graph-node graph-current">
          <strong title={graph.node.name}>{graph.node.name}</strong>
        </div>
        {neighbors.map(node => (
          <button key={node.id} type="button" className="graph-node" style={{ left: node.x, top: node.y }}
            title={node.name} disabled={disabled} onClick={() => onNavigate(node.id)}
            onFocus={event => revealFocusedNode(event, node)}>
            <strong>{node.name}</strong>
            {!node.has_source && <small>Без исходника</small>}
          </button>
        ))}
        {!neighbors.length && !loop && <span className="graph-empty">Нет прямых связей</span>}
      </div>
      {(offset.x !== 0 || offset.y !== 0) && (
        <button className="graph-reset" type="button" onClick={() => setOffset(CENTER)}>К центру</button>
      )}
    </div>
  );
}
