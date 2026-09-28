// What the agent panel sends and how it reads what comes back, as plain
// functions so they run under `npm test` (issue #83).
//
// The agent sees only the knowledge base's own MCP tools (`kos mcp`), so the
// words here only steer it: "ask" answers from pages it searched and read,
// with links; "draft" writes notes and proposes decisions. What it may do is
// fixed by the tools, never by these words.

/** Where the person is when they ask. */
export interface AgentContext {
  workspaceName: string | null;
  /** The page open in the reader, if any. */
  page: { id: string; title: string } | null;
  /** The project of that page, or the project page open. */
  project: { id: string; title: string } | null;
}

export type AgentMode = "ask" | "draft" | "review";

/** The knowledge base's tools as the agent reports them, e.g. `mcp__knowledge-os__read_page`. */
export function toolName(title: string | null): string {
  if (!title) return "";
  const match = /(?:^|__|\.|\/)([a-z_]+)$/.exec(title.trim());
  return match ? match[1] : title.trim();
}

const TOOL_LABELS: Record<string, string> = {
  search: "Searching the knowledge base",
  read_page: "Reading a page",
  list_projects: "Looking at the projects",
  list_folder: "Looking in a folder",
  write_note: "Writing a note",
  propose_decision: "Proposing a decision",
  list_proposed_decisions: "Checking the proposed decisions",
  list_proposed_changes: "Checking the proposed changes",
  read_proposed_change: "Reading a proposed change",
  check_documentation: "Checking the documentation against the code",
  read_commit: "Reading a commit",
  propose_documentation_decision: "Proposing a decision",
  mark_documentation_checked: "Recording the documentation check",
  link_repository: "Linking a repository",
};

const TOOL_REQUESTS: Record<string, string> = {
  search: "Allow the agent to search the knowledge base?",
  read_page: "Allow the agent to read a page?",
  list_projects: "Allow the agent to look at the projects?",
  list_folder: "Allow the agent to look in a folder?",
  write_note: "Allow the agent to write a note?",
  propose_decision: "Allow the agent to propose a decision?",
  list_proposed_decisions: "Allow the agent to check the proposed decisions?",
  list_proposed_changes: "Allow the agent to check the proposed changes?",
  read_proposed_change: "Allow the agent to read a proposed change?",
  check_documentation: "Allow the agent to check the documentation against the code?",
  read_commit: "Allow the agent to read a commit?",
  propose_documentation_decision: "Allow the agent to propose a decision?",
  mark_documentation_checked: "Allow the agent to record the documentation check?",
  link_repository: "Allow the agent to link a repository?",
};

/** A permission question in words. */
export function permissionQuestion(title: string | null): string {
  return TOOL_REQUESTS[toolName(title)] ?? `Allow the agent to use ${title?.trim() || "a tool"}?`;
}

/** A tool call in words: "Reading a page", or the agent's own title for anything else. */
export function toolLabel(title: string | null): string {
  const name = toolName(title);
  return TOOL_LABELS[name] ?? (title?.trim() || "Using a tool");
}

function scopeLine(context: AgentContext): string {
  if (context.page !== null) {
    const project = context.project !== null ? ` in the project "${context.project.title}" (id ${context.project.id})` : "";
    return `The person is looking at the page "${context.page.title}" (id ${context.page.id})${project}. When they say "this page", they mean it.`;
  }
  if (context.project !== null) {
    return `The person is looking at the project "${context.project.title}" (id ${context.project.id}). When they say "this project", they mean it.`;
  }
  return "The person is not looking at a particular page.";
}

const MODE_LINES: Record<AgentMode, string> = {
  review:
    "Go through what waits for the person in Decide: list_proposed_decisions and list_proposed_changes, then read each item (read_page for a decision, read_proposed_change for a change) and search for what is already in force that it repeats, contradicts, or replaces. Do not write, propose, accept, withdraw, or discard anything: the person decides, in this panel. Write one section per item, most important first, headed `### [title](/r/<id>)` for a decision or `### [title](/c/<change id>)` for a proposed change, saying in a few sentences what it is, what it would change, and any conflict or duplicate, and end each section with a line `Recommendation: accept`, `Recommendation: withdraw` (decisions), `Recommendation: discard` (changes), or `Recommendation: leave for now`, followed by one sentence why. If nothing waits, say so.",
  ask:
    "Answer from the knowledge base: search and read the relevant pages with the knowledge-os tools first, and say so when it holds no answer. Do not write anything. Link every page you used as [title](/r/<id>).",
  draft:
    "Write with the knowledge-os tools: write_note creates a note or extends one (read it first with read_page and pass its content_sha256 as expected_sha256), and propose_decision proposes a decision, which stays a proposal until the person accepts it. Afterwards say briefly what you wrote, with links [title](/r/<id>). If a write is held back for review, say that it waits in Decide.",
};

/** One turn's prompt: who and where the agent is, the mode, and the request. */
export function buildPrompt(mode: AgentMode, request: string, context: AgentContext): string {
  const base = context.workspaceName ? `the knowledge base "${context.workspaceName}"` : "the open knowledge base";
  return [
    `You are the assistant inside the Knowledge OS app, working in ${base}. Use only the knowledge-os tools.`,
    scopeLine(context),
    MODE_LINES[mode],
    "",
    request.trim(),
  ].join("\n");
}

/** The prompt that starts a new page (Ctrl+N) from one line; the agent writes nothing itself. */
export function composePrompt(request: string, context: AgentContext): string {
  return [
    `You are the assistant inside the Knowledge OS app${context.workspaceName ? `, working in the knowledge base "${context.workspaceName}"` : ""}.`,
    context.project !== null ? `The new page goes in the project "${context.project.title}".` : "",
    "Draft a new page from the request below. You may search and read the knowledge base with the knowledge-os tools for facts, but do not write, edit, or propose anything: the person reviews the draft and saves it.",
    "Reply with only the page: a first line `# <title>`, then its Markdown body.",
    "",
    request.trim(),
  ]
    .filter((line, index) => line !== "" || index > 2)
    .join("\n");
}

/** Split a composed page into its `# title` line and body, dropping anything said before it. */
export function parseComposed(text: string): { title: string; body: string } {
  // Agents sometimes say a sentence before the page; the page starts at its first `# ` heading.
  const fenced = /```(?:markdown|md)?\n([\s\S]*?)\n```/.exec(text);
  const cleaned = (fenced !== null && /^#\s/m.test(fenced[1]) ? fenced[1] : text).trim();
  const match = /^#\s+(.+)\n?([\s\S]*)$/m.exec(cleaned);
  if (match === null) return { title: "", body: cleaned ? `${cleaned}\n` : "" };
  const body = match[2].replace(/^\s*\n/, "");
  return { title: match[1].trim(), body: body ? `${body.trimEnd()}\n` : "" };
}

export interface ToolUse {
  title: string | null;
  input: unknown;
  /** The tool's result: the MCP result's JSON text, its content blocks, or an object. */
  output?: unknown;
}

function field(input: unknown, name: string): string | null {
  if (typeof input !== "object" || input === null) return null;
  const value = (input as Record<string, unknown>)[name];
  return typeof value === "string" && value.trim() !== "" ? value.trim() : null;
}

/** The result of a knowledge-os tool as an object, however the agent passes it on. */
function resultObject(output: unknown): unknown {
  if (Array.isArray(output)) {
    const text = output.map((block) => (typeof block === "object" && block !== null && "text" in block ? String(block.text) : "")).join("");
    return resultObject(text);
  }
  if (typeof output !== "string") return output;
  try {
    return JSON.parse(output) as unknown;
  } catch {
    return null;
  }
}

/** The tools that create or change a page, whose id the "Written" row links. */
const PAGE_WRITING_TOOLS = new Set(["write_note", "propose_decision", "propose_documentation_decision"]);

/** The pages a turn read and the ones it wrote to, by id, in the order used. */
export function pagesUsed(tools: readonly ToolUse[]): { read: string[]; written: string[] } {
  const read: string[] = [];
  const written: string[] = [];
  for (const tool of tools) {
    const name = toolName(tool.title);
    const id = field(tool.input, "id");
    if (name === "read_page" && id !== null && !read.includes(id)) read.push(id);
    if (PAGE_WRITING_TOOLS.has(name)) {
      // A new page's id is known only from the result; an edit names it in the input.
      const result = resultObject(tool.output);
      // A write held for review is not written yet: it waits in Decide.
      if (field(result, "action") === "waiting_for_review") continue;
      const writtenId = field(result, "id") ?? id;
      if (writtenId !== null && !written.includes(writtenId)) written.push(writtenId);
    }
  }
  return { read, written };
}

const WRITE_TOOLS = new Set([
  "write_note",
  "propose_decision",
  "propose_documentation_decision",
  "mark_documentation_checked",
  "link_repository",
]);

/** Whether a tool writes to the knowledge base (the sidebar is reloaded after one). */
export function isWriteTool(title: string | null): boolean {
  return WRITE_TOOLS.has(toolName(title));
}

/** What the documentation check asks the agent to do with one page, or with
 * all of them (issue #84): the reasons and commits come from the check. */
export function documentationPrompt(
  project: { id: string; title: string },
  repository: { path: string; label: string; head: string | null },
  pages: readonly { page: string; title: string; reasons: readonly { text: string; commits: readonly string[] }[] }[],
): string {
  const lines = [
    `The documentation check of the project "${project.title}" (id ${project.id}) against the code repository ${repository.label} suggests updating ${pages.length === 1 ? "this page" : "these pages"}:`,
    "",
  ];
  for (const page of pages) {
    lines.push(`- "${page.title}" (id ${page.page}):`);
    for (const reason of page.reasons) {
      lines.push(`  - ${reason.text} Commits: ${reason.commits.map((sha) => sha.slice(0, 12)).join(", ")}.`);
    }
  }
  lines.push(
    "",
    `Use read_commit (project ${project.id}, repository ${repository.path}) to see what changed, read_page for each page, and write_note to update it with only what the commits show. Name the commits you used at the end of each change, e.g. "(from abc1234)". Do not record the check as done; the person does that.`,
  );
  return lines.join("\n");
}

/** One turn of a conversation, as text: what the person asked and what the agent answered. */
export interface Turn {
  request: string;
  answer: string;
}

/** How much of an earlier conversation a continued one repeats, at most. */
export const EARLIER_TURNS_LIMIT = 12_000;

/**
 * A prompt for a conversation continued in a new agent session (issue #100):
 * the agent does not remember the earlier turns, so the latest of them come
 * first, cut at EARLIER_TURNS_LIMIT characters (the oldest are dropped).
 */
export function withEarlierTurns(prompt: string, turns: readonly Turn[]): string {
  const blocks: string[] = [];
  let length = 0;
  for (const turn of [...turns].reverse()) {
    const block = `Person: ${turn.request.trim()}\nYou: ${turn.answer.trim() || "(no answer)"}`;
    if (length + block.length > EARLIER_TURNS_LIMIT) break;
    blocks.unshift(block);
    length += block.length;
  }
  if (blocks.length === 0) return prompt;
  return [
    "Earlier in this conversation (repeated here, since you do not remember it):",
    "",
    blocks.join("\n\n"),
    "",
    "The conversation continues:",
    "",
    prompt,
  ].join("\n");
}

/** A page id from a title: lowercase ASCII words joined by hyphens, as the MCP tools make them. */
export function slugify(title: string): string {
  const text = title
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80)
    .replace(/-+$/, "");
  return text || "conversation";
}

/**
 * A conversation, or one answer, as a draft note (issue #100): each request as
 * a heading with its answer below, and the pages the agent used listed as
 * links (`/r/<id>`, as the app links pages).
 */
export function noteFromTurns(
  turns: readonly (Turn & { pages: readonly { id: string; title: string }[] })[],
  { agent, date }: { agent: string; date: string },
): { title: string; body: string } {
  const first = turns[0]?.request.trim() ?? "";
  const title = first.length > 80 ? `${first.slice(0, 77).trimEnd()}…` : first || "Conversation with the agent";
  const parts = [`Saved from a conversation with ${agent} in Knowledge OS on ${date}.`];
  for (const turn of turns) {
    parts.push(`## ${turn.request.trim().replace(/\s+/g, " ")}`, turn.answer.trim() || "_No answer._");
    if (turn.pages.length > 0) {
      parts.push(`Pages used: ${turn.pages.map((page) => `[${page.title}](/r/${page.id})`).join(", ")}`);
    }
  }
  return { title, body: `${parts.join("\n\n")}\n` };
}

export type Recommendation = "accept" | "withdraw" | "discard" | "leave";

/**
 * The agent's recommendations in a review answer (issue #99): each section
 * headed by a link to a decision (`/r/<id>`) or a proposed change (`/c/<id>`),
 * and its `Recommendation:` line. Items it did not recommend on are left out.
 */
export function reviewRecommendations(text: string): { kind: "decision" | "change"; id: string; recommendation: Recommendation; why: string }[] {
  const found: { kind: "decision" | "change"; id: string; recommendation: Recommendation; why: string }[] = [];
  const sections = text.split(/^#{2,4}\s+/m).slice(1);
  for (const section of sections) {
    const link = /\]\(\/(r|c)\/([A-Za-z0-9._-]+)\)/.exec(section.split("\n")[0] ?? "");
    const line = /^\**Recommendation:?\**:?\s*\**\s*(accept|withdraw|discard|leave(?: (?:it )?for now)?)\b\**\s*[.,:;—–-]*\s*(.*)$/im.exec(section);
    if (link === null || line === null) continue;
    const word = line[1].toLowerCase();
    found.push({
      kind: link[1] === "r" ? "decision" : "change",
      id: link[2],
      recommendation: word.startsWith("leave") ? "leave" : (word as Recommendation),
      why: line[2].trim(),
    });
  }
  return found;
}
