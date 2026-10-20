// Runs under Node's built-in test runner (`npm test`).

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { lineDiff, type DiffLine } from "./lineDiff.ts";

const compact = (lines: DiffLine[]) =>
  lines.map((line) => `${{ equal: " ", removed: "-", added: "+" }[line.kind]}${line.text}`);

describe("lineDiff", () => {
  it("marks every line equal when nothing changed", () => {
    assert.deepEqual(compact(lineDiff("a\nb", "a\nb")), [" a", " b"]);
  });

  it("finds lines added, removed, and replaced in the middle", () => {
    assert.deepEqual(compact(lineDiff("a\nb\nc\nd", "a\nc\nx\nd")), [" a", "-b", " c", "+x", " d"]);
  });

  it("treats an empty text as a single empty line", () => {
    assert.deepEqual(compact(lineDiff("", "one")), ["-", "+one"]);
  });

  it("keeps both sides' lines in order when they differ throughout", () => {
    assert.deepEqual(compact(lineDiff("a\nb", "c\nd")), ["-a", "-b", "+c", "+d"]);
  });

  it("can rebuild either side from the result", () => {
    const older = "intro\nkeep\nold one\nold two\nend";
    const newer = "intro\nnew\nkeep\nold two\nend\nafter";
    const lines = lineDiff(older, newer);
    const side = (kind: DiffLine["kind"]) =>
      lines.filter((line) => line.kind === "equal" || line.kind === kind).map((line) => line.text).join("\n");
    assert.equal(side("removed"), older);
    assert.equal(side("added"), newer);
  });
});
