// Runs under Node's built-in test runner (`npm test`).

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  buildPrompt,
  composePrompt,
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
