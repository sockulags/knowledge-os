import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import type { AgentBridge, AgentEvent } from "../lib/agentBridge";

vi.mock("../api/write", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/write")>()),
  write: { preview: vi.fn(() => new Promise(() => undefined)) },
}));

let emit: (event: AgentEvent) => void;
let respond: ReturnType<typeof vi.fn>;

/** The panel and its store, loaded fresh against a fake desktop bridge. */
async function loadPanel() {
  respond = vi.fn(async () => true);
  const bridge: Partial<AgentBridge> = {
    list: async () => [],
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
