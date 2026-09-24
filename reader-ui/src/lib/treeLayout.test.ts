// Runs under Node's built-in test runner (`npm test`).

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { TreeNode } from "../api/types.ts";
import {
  COMPACT_INDENT,
  findFolder,
  folderTrail,
  FULL_INDENT,
  FULL_INDENT_LEVELS,
  indentFor,
  isWithin,
  revealAfterFocus,
} from "./treeLayout.ts";

function folder(path: string, children: TreeNode[] = [], title?: string): TreeNode {
  const name = path.split("/").pop() ?? "";
  return {
    name,
    path,
    in_project: true,
    overview: title
      ? { id: `${name}-page`, title, type: "project", is_decision: false } as unknown as TreeNode["overview"]
      : null,
    records: [],
    broken: [],
    children,
  };
}

const tree: TreeNode = folder("", [
  folder("design", [folder("design/research-notes", [folder("design/research-notes/round-2")])], "Design"),
  folder("designs"),
]);

describe("indentFor", () => {
  it("uses the full step for the first levels and the compact one after", () => {
    assert.deepEqual(indentFor(1), FULL_INDENT);
    assert.deepEqual(indentFor(FULL_INDENT_LEVELS), FULL_INDENT);
    assert.deepEqual(indentFor(FULL_INDENT_LEVELS + 1), COMPACT_INDENT);
    assert.deepEqual(indentFor(12), COMPACT_INDENT);
  });

  it("keeps a visible gap on both sides of the guide at every level", () => {
    for (const indent of [FULL_INDENT, COMPACT_INDENT]) {
      assert.ok(indent.margin > 0 && indent.padding > 0);
    }
    const full = FULL_INDENT.margin + FULL_INDENT.padding;
    const compact = COMPACT_INDENT.margin + COMPACT_INDENT.padding;
    assert.ok(compact < full);
  });
});

describe("folderTrail", () => {
  it("lists every folder from the top level down, with readable titles", () => {
    assert.deepEqual(folderTrail(tree, "design/research-notes/round-2"), [
      { path: "design", title: "Design" },
      { path: "design/research-notes", title: "Research notes" },
      { path: "design/research-notes/round-2", title: "Round 2" },
    ]);
  });

  it("does not confuse a folder with one whose name starts the same", () => {
    assert.deepEqual(folderTrail(tree, "designs"), [{ path: "designs", title: "Designs" }]);
  });

  it("is null for the project itself and for a folder that no longer exists", () => {
    assert.equal(folderTrail(tree, ""), null);
    assert.equal(folderTrail(tree, "design/gone"), null);
  });
});

describe("revealAfterFocus", () => {
  it("keeps the way back down open when going up or showing the whole project", () => {
    assert.equal(revealAfterFocus("a/b/c", "a"), "a/b/c");
    assert.equal(revealAfterFocus("a/b/c", null), "a/b/c");
  });

  it("opens the new folder when going down or sideways", () => {
    assert.equal(revealAfterFocus(null, "a/b"), "a/b");
    assert.equal(revealAfterFocus("a", "a/b"), "a/b");
    assert.equal(revealAfterFocus("a/b", "ab"), "ab");
    assert.equal(revealAfterFocus(null, null), null);
  });
});

describe("isWithin", () => {
  it("matches a folder and its descendants but not a sibling with a longer name", () => {
    assert.ok(isWithin("a/b", "a/b"));
    assert.ok(isWithin("a/b/c", "a/b"));
    assert.ok(!isWithin("a/bc", "a/b"));
  });
});

describe("findFolder", () => {
  it("finds a nested folder by its path", () => {
    assert.equal(findFolder(tree, "design/research-notes/round-2")?.name, "round-2");
    assert.equal(findFolder(tree, "missing"), null);
  });
});
