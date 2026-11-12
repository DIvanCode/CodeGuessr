export const GRAPH_DURATION = 320;
export const NODE_WIDTH = 112;
export const NODE_HEIGHT = 42;

export function layoutGraph(graph) {
  const neighbors = new Map();
  const edges = new Map();
  for (const [direction, entries] of [["incoming", graph.callers], ["outgoing", graph.callees]]) {
    for (const node of entries) {
      if (node.id !== graph.node.id) neighbors.set(node.id, node);
      const source = direction === "incoming" ? node.id : graph.node.id;
      const target = direction === "incoming" ? graph.node.id : node.id;
      const key = `${source}>${target}`;
      edges.set(key, { key, source, target, opacity: 1 });
    }
  }
  const radius = Math.max(88, neighbors.size * 16);
  const nodes = [{ ...graph.node, x: 0, y: 0, current: true, opacity: 1, exiting: false }];
  Array.from(neighbors.values()).forEach((node, index) => {
    const angle = index * 2 * Math.PI / neighbors.size - Math.PI / 5;
    nodes.push({ ...node, x: Math.cos(angle) * radius * 1.65, y: Math.sin(angle) * radius,
      current: false, opacity: 1, exiting: false });
  });
  return { focusId: graph.node.id, nodes, edges: Array.from(edges.values()), offset: { x: 0, y: 0 } };
}

export function graphTransition(from, to) {
  const previous = new Map(from.nodes.map(node => [node.id, node]));
  const next = new Set(to.nodes.map(node => node.id));
  const focus = previous.get(to.focusId);
  const motions = to.nodes.map(node => ({
    start: previous.get(node.id) ?? { ...node, x: node.x * .6, y: node.y * .6, opacity: 0 },
    end: node,
  }));
  for (const node of from.nodes) {
    if (!next.has(node.id)) motions.push({ start: node,
      end: { ...node, x: node.x - (focus?.x ?? -node.x * .15),
        y: node.y - (focus?.y ?? -node.y * .15), current: false, opacity: 0, exiting: true } });
  }
  const previousEdges = new Map(from.edges.map(edge => [edge.key, edge]));
  const nextEdges = new Set(to.edges.map(edge => edge.key));
  const edges = [
    ...to.edges.map(edge => ({ ...edge, startOpacity: previousEdges.get(edge.key)?.opacity ?? 0, endOpacity: 1 })),
    ...from.edges.filter(edge => !nextEdges.has(edge.key)).map(edge => ({ ...edge, startOpacity: edge.opacity, endOpacity: 0 })),
  ];
  const mix = (a, b, progress) => a + (b - a) * progress;
  return progress => {
    if (progress >= 1) return to;
    return { focusId: to.focusId,
      offset: { x: mix(from.offset.x, 0, progress), y: mix(from.offset.y, 0, progress) },
      nodes: motions.map(({ start, end }) => ({ ...end,
        x: mix(start.x, end.x, progress), y: mix(start.y, end.y, progress),
        opacity: mix(start.opacity, end.opacity, progress) })),
      edges: edges.map(edge => ({ key: edge.key, source: edge.source, target: edge.target,
        opacity: mix(edge.startOpacity, edge.endOpacity, progress) })),
    };
  };
}

export function edgePath(source, target) {
  if (source.id === target.id) {
    const { x, y } = source;
    return `M ${x + 20} ${y - 21} C ${x + 20} ${y - 69}, ${x + 79} ${y - 62}, ${x + 56} ${y - 12}`;
  }
  const dx = target.x - source.x, dy = target.y - source.y;
  const distance = Math.max(Math.abs(dx) / (NODE_WIDTH / 2), Math.abs(dy) / (NODE_HEIGHT / 2));
  const inset = distance ? Math.min(.5, 1 / distance) : 0;
  return `M ${source.x + dx * inset} ${source.y + dy * inset} L ${target.x - dx * inset} ${target.y - dy * inset}`;
}
