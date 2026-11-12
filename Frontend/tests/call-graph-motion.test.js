import assert from "node:assert/strict";
import test from "node:test";
import { edgePath, graphTransition, layoutGraph } from "../src/call-graph-motion.js";

const node = id => ({ id, name: id, has_source: true });
const a = node("a"), b = node("b"), c = node("c"), d = node("d");
const first = layoutGraph({ node: a, callers: [], callees: [b, d] });
const second = layoutGraph({ node: b, callers: [a], callees: [c] });
const find = (scene, id) => scene.nodes.find(item => item.id === id);
const near = (actual, expected) => assert.ok(Math.abs(actual - expected) < 1e-9);

test("a clicked neighbor moves from its existing ring position to the center", () => {
  const move = graphTransition(first, second);
  const original = find(first, "b");
  near(find(move(0), "b").x, original.x);
  near(find(move(0), "b").y, original.y);
  near(find(move(.5), "b").x, original.x / 2);
  near(find(move(.5), "b").y, original.y / 2);
  assert.equal(find(move(.5), "b").opacity, 1);
  assert.equal(find(move(1), "b").x, 0);
  assert.equal(find(move(1), "b").y, 0);
  assert.equal(find(move(.5), "a").current, false);
});

test("departing nodes and edges fade out as new neighbors drift in", () => {
  const move = graphTransition(first, second);
  const half = move(.5);
  assert.equal(find(half, "d").exiting, true);
  assert.equal(find(half, "d").opacity, .5);
  assert.equal(find(half, "c").opacity, .5);
  assert.ok(Math.hypot(find(half, "c").x, find(half, "c").y) < Math.hypot(find(second, "c").x, find(second, "c").y));
  assert.equal(half.edges.find(edge => edge.key === "a>b").opacity, 1);
  assert.equal(half.edges.find(edge => edge.key === "a>d").opacity, .5);
  assert.deepEqual(move(1), second);
});

test("navigation recenters a panned camera without jumping the clicked node", () => {
  const from = { ...first, offset: { x: 80, y: -35 } };
  const move = graphTransition(from, second);
  for (const axis of ["x", "y"]) {
    const start = find(first, "b")[axis] + from.offset[axis];
    near(find(move(0), "b")[axis] + move(0).offset[axis], start);
    near(find(move(.5), "b")[axis] + move(.5).offset[axis], start / 2);
  }
  assert.deepEqual(move(1).offset, { x: 0, y: 0 });
});

test("an interrupted move starts from every visible position and opacity", () => {
  const halfway = graphTransition({ ...first, offset: { x: 60, y: 30 } }, second)(.4);
  const next = layoutGraph({ node: c, callers: [b], callees: [] });
  const move = graphTransition(halfway, next);
  for (const previous of halfway.nodes) {
    const current = find(move(0), previous.id);
    near(current.x, previous.x);
    near(current.y, previous.y);
    near(current.opacity, previous.opacity);
  }
  assert.deepEqual(move(0).offset, halfway.offset);
  assert.deepEqual(move(1), next);
});

test("recursive and mutual calls retain one node per symbol and both directions", () => {
  const scene = layoutGraph({ node: a, callers: [a, b], callees: [a, b] });
  assert.equal(scene.nodes.length, 2);
  assert.deepEqual(scene.edges.map(edge => edge.key).sort(), ["a>a", "a>b", "b>a"]);
  const empty = layoutGraph({ node: a, callers: [], callees: [] });
  assert.equal(empty.nodes.length, 1);
  assert.equal(empty.edges.length, 0);
});

test("arrows meet node boundaries and handle overlapping positions", () => {
  const horizontal = edgePath({ id: "a", x: 0, y: 0 }, { id: "b", x: 200, y: 0 }).match(/-?\d+(?:\.\d+)?/g).map(Number);
  horizontal.forEach((value, index) => near(value, [56, 0, 144, 0][index]));
  assert.equal(edgePath({ id: "a", x: 0, y: 0 }, { id: "b", x: 0, y: 100 }), "M 0 21 L 0 79");
  assert.equal(edgePath({ id: "a", x: 0, y: 0 }, { id: "b", x: 0, y: 0 }), "M 0 0 L 0 0");
  assert.equal(edgePath({ id: "a", x: 10, y: 20 }, { id: "a", x: 10, y: 20 }), "M 30 -1 C 30 -49, 89 -42, 66 8");
});

test("arrows remain attached to existing nodes throughout interrupted transitions", () => {
  let frame = first;
  for (let index = 0; index < 20; index++) {
    const next = index % 2 ? first : second;
    const move = graphTransition(frame, next);
    frame = move(.35);
    assert.equal(new Set(frame.nodes.map(item => item.id)).size, frame.nodes.length);
    for (const edge of frame.edges) {
      const source = find(frame, edge.source), target = find(frame, edge.target);
      assert.ok(source && target);
      assert.ok(!/NaN|Infinity/.test(edgePath(source, target)));
      assert.ok(edge.opacity >= 0 && edge.opacity <= 1);
    }
  }
});
