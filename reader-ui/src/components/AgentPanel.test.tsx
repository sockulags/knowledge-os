import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import type { ReviewRulesPayload } from "../api/types";
import type { AgentBridge, AgentEvent, AgentProviderInfo } from "../lib/agentBridge";

const reviewRules = vi.hoisted(() => ({ current: { rules: [], error: null } as ReviewRulesPayload }));

vi.mock("../api/client", async (importOriginal) => {
  const original = await importOriginal<typeof import("../api/client")>();
  return { ...original, api: { ...original.api, reviewRules: async () => reviewRules.current } };
});

vi.mock("../api/write", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/write")>()),
  write: { preview: vi.fn(() => new Promise(() => undefined)) },
}));

let emit: (event: AgentEvent) => void;
let respond: ReturnType<typeof vi.fn>;

/** The panel and its store, loaded fresh against a fake desktop bridge. */
async function loadPanel(providers: AgentProviderInfo[] = []) {
  respond = vi.fn(async () => true);
  const bridge: Partial<AgentBridge> = {
    list: async () => providers,
    respondPermission: respond as AgentBridge["respondPermission"],
    conversations: async () => [],
    onEvent: (callback) => {
      emit = callback;
      return () => undefined;
    },
  };
  (window as { kosDesktop?: unknown }).kosDesktop = { agent: bridge };
  vi.resetModules();
  const { AgentPanel } = await import("./AgentPanel");
  render(
    <MemoryRouter>
      <AgentPanel open onClose={() => undefined} context={{ workspaceName: null, page: null, project: null }} nav={null} />
    </MemoryRouter>,
  );
}

function ask(title: string, input: unknown) {
  act(() =>
    emit({
      type: "permission",
      requestId: "permission-1",
      toolCallId: "call-1",
      title,
      input,
      options: [
        { id: "once", name: "Allow", kind: "allow_once" },
        { id: "always", name: "Always allow", kind: "allow_always" },
        { id: "reject", name: "Reject", kind: "reject_once" },
      ],
    }),
  );
  return screen.getByTestId("agent-permission");
}

beforeEach(() => {
  vi.clearAllMocks();
  // jsdom has no layout, so no scrolling.
  Element.prototype.scrollIntoView = () => undefined;
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  delete (window as { kosDesktop?: unknown }).kosDesktop;
});

describe("AgentPanel permission question", () => {
  it("shows the note the agent would write before it is allowed", async () => {
    await loadPanel();
    const body = `Retry twice, then stop. <img src=x onerror="alert(1)">\n${"More text. ".repeat(80)}`;
    const card = ask("mcp__knowledge-os__write_note", { title: "Retry policy", content: body, project: "demo" });

    expect(within(card).getByText("Allow the agent to write a note?")).toBeTruthy();
    expect(within(card).getByText("New note in the project demo")).toBeTruthy();
    expect(within(card).getByText("Retry policy")).toBeTruthy();
    // The text is shown as text, never as markup, and long text is cut until asked for.
    const text = within(card).getByLabelText("Text it would write");
    expect(text.textContent).toContain('<img src=x onerror="alert(1)">');
    expect(card.querySelector("img")).toBeNull();
    expect(text.textContent).not.toBe(body);
    fireEvent.click(within(card).getByRole("button", { name: /Show all/ }));
    expect(within(card).getByLabelText("Text it would write").textContent).toBe(body);

    fireEvent.click(within(card).getByRole("button", { name: "Allow" }));
    expect(respond).toHaveBeenCalledWith("permission-1", "once");
  });

  it("shows the command another tool would run", async () => {
    await loadPanel();
    const card = ask("Bash", { command: "rm -rf build", description: "Clean the build" });
    expect(within(card).getByLabelText("Command it would run").textContent).toBe("rm -rf build");
  });

  it("makes allowing once the main answer and allowing always a secondary one", async () => {
    await loadPanel();
    const card = ask("mcp__knowledge-os__write_note", null);
    expect(within(card).queryByTestId("agent-permission-input")).toBeNull();
    const button = (name: string) => within(card).getByRole("button", { name });
    expect(button("Allow").className).toContain("kos-btn-primary");
    expect(button("Always allow").className).toContain("kos-btn-secondary");
    expect(button("Always allow").className).not.toContain("kos-btn-primary");
    expect(button("Reject").className).toContain("kos-btn-secondary");
  });
});

describe("AgentPanel review rules", () => {
  it("says under the header that agent writes land directly when there are no rules", async () => {
    reviewRules.current = { rules: [], error: null };
    await loadPanel();
    const line = within(await screen.findByTestId("review-rules")).getByRole("button", {
      name: "No review rules: agent and person writes land directly.",
    });
    fireEvent.click(line);
    expect(screen.getByTestId("review-rules").querySelector("pre")?.textContent).toContain('writer = "agent"');
  });

  it("opens the rules that apply", async () => {
    reviewRules.current = {
      rules: [
        {
          number: 1,
          writer: "agent",
          project: null,
          folder: null,
          writes: "any",
          action: "review",
          description: "Rule 1: notes by agents wait for review in Decide.",
        },
      ],
      error: null,
    };
    await loadPanel();
    const section = await screen.findByTestId("review-rules");
    const toggle = within(section).getByRole("button", { name: "1 review rule applies." });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(toggle);
    expect(within(section).getByText("Rule 1: notes by agents wait for review in Decide.")).toBeTruthy();
  });

  it("says when the rules cannot be used", async () => {
    reviewRules.current = { rules: [], error: "review rule 1: writer must be agent" };
    await loadPanel();
    const section = await screen.findByTestId("review-rules");
    fireEvent.click(within(section).getByRole("button", { name: "The review rules cannot be used." }));
    expect(within(section).getByText(/review rule 1: writer must be agent/)).toBeTruthy();
  });
});

function provider(id: string, displayName: string): AgentProviderInfo {
  return {
    id,
    displayName,
    state: "ready",
    version: "1.0.0",
    message: displayName,
    adapterVersion: "1.0.0",
    adapterInstalled: true,
    mcpClientName: `${id}-client`,
  };
}

describe("AgentPanel with Codex", () => {
  it("asks the person to turn Codex on before it can be used, then keeps a notice", async () => {
    await loadPanel([provider("codex", "Codex")]);
    const card = await screen.findByTestId("agent-codex-opt-in");
    expect(within(card).getByText(/can read any file your account can/)).toBeTruthy();
    expect(screen.getByRole("textbox", { name: "Question" })).toHaveProperty("disabled", true);

    fireEvent.click(within(card).getByRole("checkbox", { name: "Use Codex with this access" }));

    expect(screen.queryByTestId("agent-codex-opt-in")).toBeNull();
    expect(screen.getByTestId("agent-codex-notice").textContent).toContain("can read files outside this knowledge base");
    expect(screen.getByRole("textbox", { name: "Question" })).toHaveProperty("disabled", false);
    expect(window.localStorage.getItem("kos.agent.codexTurnedOn")).toBe("yes");
  });

  it("remembers that Codex was turned on", async () => {
    window.localStorage.setItem("kos.agent.codexTurnedOn", "yes");
    await loadPanel([provider("codex", "Codex")]);
    expect(await screen.findByTestId("agent-codex-notice")).toBeTruthy();
    expect(screen.queryByTestId("agent-codex-opt-in")).toBeNull();
  });

  it("shows no notice for Claude Code", async () => {
    await loadPanel([provider("claude-code", "Claude Code"), provider("codex", "Codex")]);
    expect(await screen.findAllByText("Claude Code")).not.toHaveLength(0);
    expect(screen.queryByTestId("agent-codex-notice")).toBeNull();
    expect(screen.queryByTestId("agent-codex-opt-in")).toBeNull();
    expect(screen.getByRole("textbox", { name: "Question" })).toHaveProperty("disabled", false);
  });
});
