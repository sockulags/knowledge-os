// Runs under Node's built-in test runner (`npm test`), which strips the
// TypeScript types itself; no test framework is installed for the reader UI.

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { RecordIndexEntry, SearchResult } from "../api/types.ts";
import {
  buildSections,
  hrefFor,
  isMacPlatform,
  isQuickSwitchShortcut,
  rankTitles,
  scoreTitle,
  TITLE_LIMIT_PER_GROUP,
} from "./quickSwitch.ts";

function entry(id: string, title: string, group: string, kind = "knowledge"): RecordIndexEntry {
  return { id, title, kind, status_pill: null, project: null, group, kind_label: "Label" };
}

function hit(id: string, title: string): SearchResult {
  return {
    id,
    title,
    type: "knowledge",
    type_label: "Knowledge",
    status: "active",
    status_label: "Current",
    record_kind: null,
    record_kind_label: "",
    trust_label: "",
    scope: "general",
    project: null,
    project_id: null,
    snippet_html: "a <mark>word</mark> in the text",
  };
}

describe("scoreTitle", () => {
  it("ranks exact, prefix, word start, substring, then scattered words", () => {
    const scores = [
      scoreTitle("Release notes", "release notes"),
      scoreTitle("Release notes", "rele"),
      scoreTitle("Release notes", "note"),
      scoreTitle("Release notes", "ease"),
      scoreTitle("Release notes", "not rel"),
    ];
    assert.deepEqual([...scores].sort((a, b) => b - a), scores);
    assert.ok(scores.every((score) => score > 0));
  });

  it("ignores case and accents", () => {
    assert.ok(scoreTitle("Planeringsmöte vecka 39", "MOTE") > 0);
    assert.ok(scoreTitle("Café rules", "cafe") > 0);
  });

  it("does not match when a typed word is missing or the query is blank", () => {
    assert.equal(scoreTitle("Release notes", "release plan"), 0);
    assert.equal(scoreTitle("Release notes", "   "), 0);
  });
});

describe("rankTitles", () => {
  it("puts the best match first and breaks ties with the shorter title", () => {
    const ranked = rankTitles(
      [
        entry("a", "Notes on the reader", "pages"),
        entry("b", "Reader", "pages"),
        entry("c", "Reader architecture", "pages"),
        entry("d", "Unrelated", "pages"),
      ],
      "reader",
    );
    assert.deepEqual(
      ranked.map((item) => item.entry.id),
      ["b", "c", "a"],
    );
  });
});

describe("buildSections", () => {
  const index = [
    entry("kos", "Knowledge OS", "projects", "project"),
    entry("use-sqlite", "Use SQLite for the index", "decisions", "decision"),
    entry("index-notes", "Index notes", "pages"),
    entry("indexing", "indexing", "skills", "skill"),
    entry("README.md", "Index of documents", "docs", "doc"),
  ];

  it("groups title matches and orders groups by their best match", () => {
    const sections = buildSections(index, "index", null);
    assert.deepEqual(
      sections.map((section) => section.group),
      ["pages", "skills", "docs", "decisions"],
    );
    assert.equal(sections[0].options[0].href, "/r/index-notes");
  });

  it("orders equally good groups by the fixed group order", () => {
    const sections = buildSections(
      [entry("p", "Alpha", "pages"), entry("d", "Alpha", "decisions", "decision"), entry("x", "Alpha", "projects", "project")],
      "alpha",
      null,
    );
    assert.deepEqual(
      sections.map((section) => section.group),
      ["projects", "decisions", "pages"],
    );
  });

  it("caps each title group", () => {
    const many = Array.from({ length: 12 }, (_, n) => entry(`n${n}`, `Note ${n}`, "pages"));
    const [section] = buildSections(many, "note", null);
    assert.equal(section.options.length, TITLE_LIMIT_PER_GROUP);
  });

  it("adds text-only hits after the title groups, without repeating a title match", () => {
    const sections = buildSections(index, "sqlite", [hit("use-sqlite", "Use SQLite for the index"), hit("other", "Storage")]);
    assert.deepEqual(
      sections.map((section) => section.group),
      ["decisions", "text"],
    );
    const text = sections[1].options;
    assert.deepEqual(
      text.map((option) => option.entry.id),
      ["other"],
    );
    assert.equal(text[0].href, "/r/other");
    assert.equal(text[0].entry.kind_label, "Knowledge");
    assert.match(text[0].snippetHtml ?? "", /<mark>/);
  });

  it("uses the index entry for a text hit it knows, so a project opens its project page", () => {
    const sections = buildSections(index, "zzz", [hit("kos", "Knowledge OS")]);
    assert.equal(sections.length, 1);
    assert.equal(sections[0].group, "text");
    assert.equal(sections[0].options[0].href, "/p/kos");
  });

  it("gives every option a unique key", () => {
    const sections = buildSections(index, "index", [hit("x1", "One"), hit("x2", "Two")]);
    const keys = sections.flatMap((section) => section.options.map((option) => option.key));
    assert.equal(new Set(keys).size, keys.length);
  });
});

describe("hrefFor", () => {
  it("links each kind to its page", () => {
    assert.equal(hrefFor({ id: "kos", kind: "project", group: "projects" }), "/p/kos");
    assert.equal(hrefFor({ id: "plan", kind: "project", group: "pages" }), "/r/plan");
    assert.equal(hrefFor({ id: "ingest", kind: "skill", group: "skills" }), "/s/ingest");
    assert.equal(hrefFor({ id: "docs/a.md", kind: "doc", group: "docs" }), "/f/docs/a.md");
    assert.equal(hrefFor({ id: "d1", kind: "decision", group: "decisions" }), "/r/d1");
  });
});

describe("isQuickSwitchShortcut", () => {
  const key = (init: Partial<KeyboardEvent>) => ({ key: "k", ctrlKey: false, metaKey: false, altKey: false, shiftKey: false, ...init });

  it("is Ctrl K off macOS and Cmd K on macOS", () => {
    assert.equal(isQuickSwitchShortcut(key({ ctrlKey: true }), false), true);
    assert.equal(isQuickSwitchShortcut(key({ key: "K", ctrlKey: true }), false), true);
    assert.equal(isQuickSwitchShortcut(key({ metaKey: true }), false), false);
    assert.equal(isQuickSwitchShortcut(key({ metaKey: true }), true), true);
    assert.equal(isQuickSwitchShortcut(key({ ctrlKey: true }), true), false);
    assert.equal(isQuickSwitchShortcut(key({ ctrlKey: true, shiftKey: true }), false), false);
    assert.equal(isQuickSwitchShortcut(key({}), false), false);
  });

  it("recognises Apple platforms", () => {
    assert.equal(isMacPlatform("MacIntel"), true);
    assert.equal(isMacPlatform("Win32"), false);
  });
});
