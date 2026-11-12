import { useCallback, useId, useLayoutEffect, useMemo, useRef, useState } from "react";
import { GRAPH_DURATION, NODE_HEIGHT, NODE_WIDTH, edgePath, graphTransition, layoutGraph } from "./call-graph-motion.js";

const CENTER = { x: 0, y: 0 };

function useGraphScene(graph) {
  const target = useMemo(() => layoutGraph(graph), [graph]);
  const [scene, setScene] = useState(target);
  const current = useRef(target);
  const cameraOverride = useRef(false);

  const setOffset = useCallback(value => {
    // Dragging takes control of the camera while node transitions can finish.
    cameraOverride.current = true;
    const offset = typeof value === "function" ? value(current.current.offset) : value;
    current.current = { ...current.current, offset };
    setScene(current.current);
  }, []);

  useLayoutEffect(() => {
    const signature = frame => JSON.stringify([frame.focusId, frame.nodes, frame.edges]);
    if (signature(current.current) === signature(target)) return;
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    cameraOverride.current = false;
    let animation;
    const show = value => {
      current.current = cameraOverride.current ? { ...value, offset: current.current.offset } : value;
      setScene(current.current);
    };
    const finish = () => { cancelAnimationFrame(animation); show(target); };
    if (preference.matches) {
      finish();
      return;
    }
    // A second click starts at the actual visible frame, avoiding position jumps.
    const interpolate = graphTransition(current.current, target);
    const started = performance.now();
    const tick = now => {
      const progress = Math.max(0, Math.min(1, (now - started) / GRAPH_DURATION));
      show(interpolate(1 - (1 - progress) ** 3));
      if (progress < 1) animation = requestAnimationFrame(tick);
    };
    const onPreferenceChange = () => { if (preference.matches) finish(); };
    show(interpolate(0));
    animation = requestAnimationFrame(tick);
    preference.addEventListener("change", onPreferenceChange);
    return () => {
      cancelAnimationFrame(animation);
      preference.removeEventListener("change", onPreferenceChange);
    };
  }, [target]);

  return [scene, setOffset];
}

export function CallGraph({ graph, onNavigate, disabled }) {
  const arrowId = useId();
  const [scene, setOffset] = useGraphScene(graph);
  const { offset } = scene;
  const [dragging, setDragging] = useState(false);
  const pointer = useRef(null);
  const suppressClick = useRef(false);
  const nodes = new Map(scene.nodes.map(node => [node.id, node]));

  function startPan(event) {
    if (!event.isPrimary || event.button !== 0) return;
    suppressClick.current = false;
    if (event.target.closest(".graph-reset")) return;
    setOffset(offset);
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
          {scene.edges.map(edge => (
            <path key={edge.key} className="graph-edge" opacity={edge.opacity}
              d={edgePath(nodes.get(edge.source), nodes.get(edge.target))}
              markerEnd={`url(#${arrowId})`} />
          ))}
        </svg>
        {scene.nodes.map(node => (
          <button key={node.id} type="button" data-node-id={node.id}
            className={`graph-node${node.current ? " graph-current" : ""}${node.exiting ? " graph-exiting" : ""}`}
            style={{ left: node.x, top: node.y, opacity: node.opacity }}
            aria-current={node.current ? "true" : undefined} aria-hidden={node.exiting || undefined}
            tabIndex={node.exiting ? -1 : 0} title={node.name} disabled={disabled || node.exiting}
            onClick={() => { if (!node.current) onNavigate(node.id); }}
            onFocus={event => revealFocusedNode(event, node)}>
            <strong>{node.name}</strong>
            {!node.has_source && !node.current && <small>Без исходника</small>}
          </button>
        ))}
        {scene.nodes.length === 1 && !scene.edges.length && <span className="graph-empty">Нет прямых связей</span>}
      </div>
      {(offset.x !== 0 || offset.y !== 0) && (
        <button className="graph-reset" type="button" onClick={() => setOffset(CENTER)}>К центру</button>
      )}
    </div>
  );
}
