import { beforeEach, describe, expect, it, vi } from "vitest";
import { write } from "../api/write";
import { agentStore, type AgentState } from "./agentStore";

vi.mock("../api/write", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/write")>()),
  write: { create: vi.fn() },
}));

const create = write.create as unknown as ReturnType<typeof vi.fn>;

function withConversation(changes: Partial<AgentState> = {}) {
  const store = agentStore as unknown as { state: AgentState };
  store.state = {
    ...store.state,
    transcript: [
      { kind: "user", id: 1, text: "How do we retry deploys?", mode: "ask" },
      { kind: "agent", id: 2, text: "Retry twice, then stop.", done: true, tools: [], permissions: [] },
    ],
    ...changes,
  } as AgentState;
}

beforeEach(() => {
  create.mockReset();
  create.mockResolvedValue({ ok: true, data: { id: "saved-note" } });
});

describe("agentStore.saveAsNote", () => {
  it("saves the note active in the project in view, so only the review rules can hold it back", async () => {
    withConversation({
      providers: [{ id: "claude", displayName: "Claude Code", mcpClientName: "claude-code" }] as AgentState["providers"],
      providerId: "claude",
    });

    const result = await agentStore.saveAsNote(null, { workspaceName: null, page: null, project: { id: "demo", title: "Demo" } } as never, new Map());

    expect(result).toEqual({ id: "saved-note" });
    const request = create.mock.calls[0][0];
    expect(request.metadata.status).toBe("active");
    expect(request.metadata.type).toBe("project");
    expect(request.metadata.scope).toBe("project:demo");
    expect(request.agent).toEqual({ client: "claude-code", place: "Knowledge OS app" });
  });

  it("reports a note the review rules held back", async () => {
    withConversation({ providers: null, providerId: null });
    create.mockResolvedValue({ ok: true, data: { status: "proposed", proposal: { id: "p1" } } });

    const result = await agentStore.saveAsNote(null, { workspaceName: null, page: null, project: null } as never, new Map());

    expect(result).toBe("held");
    const request = create.mock.calls[0][0];
    expect(request.metadata.status).toBe("active");
    expect(request.metadata.scope).toBe("general");
  });
});
