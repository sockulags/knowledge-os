// Runs under Node's built-in test runner (`npm test`).

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  EARLIER_TURNS_LIMIT,
  buildPrompt,
  composePrompt,
  documentationPrompt,
  noteFromTurns,
  slugify,
  withEarlierTurns,
  isWriteTool,
  pagesUsed,
  parseComposed,
  permissionQuestion,
  toolLabel,
  toolName,
} from "./agentPrompt.ts";

const onPage = {
  workspaceName: "notes",
  page: { id: "retry-policy", title: "Retry policy" },
  project: { id: "demo", title: "Demo" },
};

describe("buildPrompt", () => {
  it("names the knowledge base, the page in view, and the mode", () => {
    const ask = buildPrompt("ask", "  How do retries work?  ", onPage);
    assert.match(ask, /knowledge base "notes"/);
    assert.match(ask, /page "Retry policy" \(id retry-policy\) in the project "Demo"/);
    assert.match(ask, /Do not write anything/);
    assert.match(ask, /\[title\]\(\/r\/<id>\)/);
    assert.ok(ask.endsWith("\nHow do retries work?"));

    const draft = buildPrompt("draft", "Add a section", { workspaceName: null, page: null, project: onPage.project });
    assert.match(draft, /project "Demo" \(id demo\)/);
    assert.match(draft, /write_note/);
    assert.match(draft, /waits in Decide/);
  });

  it("asks a composed page to write nothing", () => {
    const prompt = composePrompt("Meeting notes for the retro", onPage);
    assert.match(prompt, /do not write, edit, or propose anything/);
    assert.match(prompt, /# <title>/);
    assert.ok(prompt.endsWith("Meeting notes for the retro"));
  });
});

describe("parseComposed", () => {
  it("splits the title line from the body", () => {
    assert.deepEqual(parseComposed("# Retro\n\n## Went well\n- Shipping\n"), { title: "Retro", body: "## Went well\n- Shipping\n" });
    assert.deepEqual(parseComposed("```markdown\n# Retro\nText\n```"), { title: "Retro", body: "Text\n" });
    assert.deepEqual(parseComposed("No heading here"), { title: "", body: "No heading here\n" });
    assert.deepEqual(parseComposed("Here's the draft:\n\n# Retry policy\nText"), { title: "Retry policy", body: "Text\n" });
    assert.deepEqual(parseComposed("Sure.\n```md\n# Retro\nText\n```\nDone."), { title: "Retro", body: "Text\n" });
  });
});

describe("tools", () => {
  it("reads MCP tool names however the agent prefixes them", () => {
    assert.equal(toolName("mcp__knowledge-os__read_page"), "read_page");
    assert.equal(toolName("knowledge-os/search"), "search");
    assert.equal(toolLabel("mcp__knowledge-os__write_note"), "Writing a note");
    assert.equal(toolLabel("Something else"), "Something else");
    assert.equal(permissionQuestion("mcp__knowledge-os__read_page"), "Allow the agent to read a page?");
    assert.equal(permissionQuestion("Bash"), "Allow the agent to use Bash?");
    assert.ok(isWriteTool("mcp__knowledge-os__propose_decision"));
    assert.ok(!isWriteTool("mcp__knowledge-os__search"));
  });

  it("lists the pages a turn read and wrote, once each", () => {
    const used = pagesUsed([
      { title: "mcp__knowledge-os__search", input: { query: "retry" } },
      { title: "mcp__knowledge-os__read_page", input: { id: "retry-policy" } },
      { title: "mcp__knowledge-os__read_page", input: { id: "retry-policy" } },
      { title: "mcp__knowledge-os__write_note", input: { id: "retry-policy", content: "x" } },
      { title: "mcp__knowledge-os__read_page", input: null },
    ]);
    assert.deepEqual(used, { read: ["retry-policy"], written: ["retry-policy"] });
  });

  it("takes a new page's id from the tool's result", () => {
    const created = JSON.stringify({ ok: true, action: "created", id: "retry-runbook" });
    const used = pagesUsed([
      { title: "mcp__knowledge-os__write_note", input: { title: "Retry runbook" }, output: created },
      { title: "mcp__knowledge-os__propose_decision", input: { title: "Cap" }, output: [{ type: "text", text: '{"id":"cap"}' }] },
      { title: "mcp__knowledge-os__write_note", input: { title: "Held" }, output: '{"ok":false,"waiting_for_review":true}' },
    ]);
    assert.deepEqual(used, { read: [], written: ["retry-runbook", "cap"] });
  });
});

describe("documentation check", () => {
  it("counts the check's tools and links the decision it proposes", () => {
    assert.equal(toolLabel("mcp__knowledge-os__check_documentation"), "Checking the documentation against the code");
    assert.ok(isWriteTool("mcp__knowledge-os__propose_documentation_decision"));
    assert.ok(isWriteTool("mcp__knowledge-os__mark_documentation_checked"));
    assert.ok(!isWriteTool("mcp__knowledge-os__read_commit"));
    const used = pagesUsed([
      { title: "mcp__knowledge-os__propose_documentation_decision", input: { key: "dependency-added:httpx" }, output: '{"id":"add-the-dependency-httpx"}' },
      { title: "mcp__knowledge-os__mark_documentation_checked", input: { commit: "abc" }, output: '{"id":"demo"}' },
    ]);
    assert.deepEqual(used.written, ["add-the-dependency-httpx"]);
  });

  it("asks for page updates with their reasons and commits", () => {
    const prompt = documentationPrompt(
      { id: "demo", title: "Demo" },
      { path: "../code", label: "code", head: "f".repeat(40) },
      [{ page: "http", title: "HTTP layer", reasons: [{ text: "Mentions the dependency `requests` removed.", commits: ["a".repeat(40)] }] }],
    );
    assert.match(prompt, /project "Demo" \(id demo\) against the code repository code suggests updating this page:/);
    assert.match(prompt, /- "HTTP layer" \(id http\):\n  - Mentions the dependency `requests` removed\. Commits: a{12}\./);
    assert.match(prompt, /read_commit \(project demo, repository \.\.\/code\)/);
    assert.match(prompt, /Do not record the check as done/);
  });
});

describe("conversations", () => {
  it("repeats the latest earlier turns when a conversation continues", () => {
    assert.equal(withEarlierTurns("Next?", []), "Next?");
    const prompt = withEarlierTurns("Next?", [
      { request: "How many retries?", answer: "Three." },
      { request: "And the backoff?", answer: "" },
    ]);
    assert.match(prompt, /^Earlier in this conversation/);
    assert.match(prompt, /Person: How many retries\?\nYou: Three\.\n\nPerson: And the backoff\?\nYou: \(no answer\)/);
    assert.ok(prompt.endsWith("The conversation continues:\n\nNext?"));

    const long = "x".repeat(EARLIER_TURNS_LIMIT / 2);
    const cut = withEarlierTurns("Now", [
      { request: "oldest", answer: long },
      { request: "middle", answer: long },
      { request: "latest", answer: "short" },
    ]);
    assert.ok(!cut.includes("oldest") && cut.includes("middle") && cut.includes("latest"));
  });

  it("makes page ids from titles", () => {
    assert.equal(slugify("Hur fungerar återförsök?"), "hur-fungerar-aterforsok");
    assert.equal(slugify("!!!"), "conversation");
  });

  it("turns a conversation into a note with its pages linked", () => {
    const note = noteFromTurns(
      [
        { request: "How do retries work?", answer: "Three times, see [Retry policy](/r/retry-policy).", pages: [{ id: "retry-policy", title: "Retry policy" }] },
        { request: "Who is paged?", answer: "", pages: [] },
      ],
      { agent: "Claude Code", date: "2026-09-28" },
    );
    assert.equal(note.title, "How do retries work?");
    assert.equal(
      note.body,
      "Saved from a conversation with Claude Code in Knowledge OS on 2026-09-28.\n\n" +
        "## How do retries work?\n\nThree times, see [Retry policy](/r/retry-policy).\n\n" +
        "Pages used: [Retry policy](/r/retry-policy)\n\n" +
        "## Who is paged?\n\n_No answer._\n",
    );
    assert.equal(noteFromTurns([{ request: "y".repeat(100), answer: "a", pages: [] }], { agent: "Codex", date: "d" }).title.length, 78);
  });
});
