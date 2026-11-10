import assert from "node:assert/strict";
import test from "node:test";

import { maxShare, setShare, totalShare } from "../src/language-shares.js";

test("unassigned share fills the rest of the pie", () => {
  const shares = setShare({}, "Python", 10);
  assert.equal(100 - totalShare(shares), 90);
  const decreased = setShare(shares, "Python", 3);
  assert.equal(100 - totalShare(decreased), 97);
  assert.equal(shares.Python, 10);
});

test("adding or growing a language in a full pie leaves other languages visible", () => {
  const full = { "C++": 98, C: 2 };
  const added = setShare(full, "Python", 10);
  assert.deepEqual(added, { "C++": 88, C: 2, Python: 10 });

  const grown = setShare(added, "Python", maxShare(added, "Python"));
  assert.deepEqual(grown, { "C++": 1, C: 1, Python: 98 });
  assert.equal(totalShare(grown), 100);
});
