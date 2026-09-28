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

export type AgentMode = "ask" | "draft";

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
};

const TOOL_REQUESTS: Record<string, string> = {
  search: "Allow the agent to search the knowledge base?",
  read_page: "Allow the agent to read a page?",
  list_projects: "Allow the agent to look at the projects?",
  list_folder: "Allow the agent to look in a folder?",
  write_note: "Allow the agent to write a note?",
  propose_decision: "Allow the agent to propose a decision?",
  list_proposed_decisions: "Allow the agent to check the proposed decisions?",
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

/** The pages a turn read and the ones it wrote to, by id, in the order used. */
export function pagesUsed(tools: readonly ToolUse[]): { read: string[]; written: string[] } {
  const read: string[] = [];
  const written: string[] = [];
  for (const tool of tools) {
    const name = toolName(tool.title);
    const id = field(tool.input, "id");
    if (name === "read_page" && id !== null && !read.includes(id)) read.push(id);
    if (name === "write_note" || name === "propose_decision") {
      // A new page's id is known only from the result; an edit names it in the input.
      const writtenId = field(resultObject(tool.output), "id") ?? id;
      if (writtenId !== null && !written.includes(writtenId)) written.push(writtenId);
    }
  }
  return { read, written };
}

/** Whether a tool writes to the knowledge base (the sidebar is reloaded after one). */
export function isWriteTool(title: string | null): boolean {
  const name = toolName(title);
  return name === "write_note" || name === "propose_decision";
}
