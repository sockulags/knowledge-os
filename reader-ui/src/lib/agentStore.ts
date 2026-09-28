// The agent panel's state, kept outside React so the panel and New page (a
// page started by the agent, Ctrl+N) share one session (issue #83). It talks
// to the desktop app through agentBridge.ts and holds the conversation the
// panel shows. Nothing here is saved: a conversation ends with the session.

import { useSyncExternalStore } from "react";
import {
  agentBridge,
  bridgeError,
  type AgentBridge,
  type AgentEvent,
  type AgentProviderInfo,
  type AuthHelp,
  type SessionState,
} from "./agentBridge";
import { buildPrompt, composePrompt, isWriteTool, parseComposed, type AgentContext, type AgentMode } from "./agentPrompt";

export type TranscriptItem =
  | { kind: "user"; id: number; text: string; mode: AgentMode }
  | { kind: "agent"; id: number; text: string; done: boolean; tools: ToolItem[]; permissions: PermissionAsk[] }
  | { kind: "notice"; id: number; text: string; tone: "info" | "error" };

/** A question the agent put to the person during its answer, shown with that answer. */
export interface PermissionAsk {
  requestId: string;
  /** The tool call it is about, whose row shows the answer once given. */
  toolCallId: string | null;
  title: string;
  options: { id: string; name: string; kind: string }[];
  /** "allowed", "allowed from now on", "refused", or "cancelled"; null while it waits. */
  answer: string | null;
}

/** A transcript item before it has an id (distributes over the union). */
type WithoutId<T> = T extends unknown ? Omit<T, "id"> : never;

export interface ToolItem {
  id: string;
  title: string | null;
  status: string | null;
  input: unknown;
  output: unknown;
}

export interface AgentState {
  available: boolean;
  providers: AgentProviderInfo[] | null;
  /** The provider the person chose, remembered in this browser. */
  providerId: string | null;
  /** The running session's provider, or null. */
  sessionProvider: string | null;
  session: SessionState | "none";
  auth: AuthHelp | null;
  install: { providerId: string; done: number; total: number } | null;
  busy: boolean;
  transcript: TranscriptItem[];
  error: string | null;
}

const PROVIDER_KEY = "kos.agent.provider";

function rememberedProvider(): string | null {
  try {
    return window.localStorage.getItem(PROVIDER_KEY);
  } catch {
    return null;
  }
}

class AgentStore {
  private state: AgentState;
  private listeners = new Set<() => void>();
  private nextId = 1;
  private bridge: AgentBridge | null;
  /** How many tool calls each agent message had at its last text. */
  private textTools = new Map<number, number>();
  /** Called after the agent wrote something, to reload the sidebar. */
  onWrite: (() => void) | null = null;
  /** Opens the panel, for a request started elsewhere in the reader. */
  onOpen: (() => void) | null = null;

  constructor() {
    this.bridge = agentBridge();
    this.state = {
      available: this.bridge !== null,
      providers: null,
      providerId: rememberedProvider(),
      sessionProvider: null,
      session: "none",
      auth: null,
      install: null,
      busy: false,
      transcript: [],
      error: null,
    };
    this.bridge?.onEvent((event) => this.handle(event));
  }

  snapshot = (): AgentState => this.state;

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  private set(changes: Partial<AgentState>): void {
    this.state = { ...this.state, ...changes };
    for (const listener of this.listeners) listener();
  }

  private push(item: WithoutId<TranscriptItem>): void {
    this.set({ transcript: [...this.state.transcript, { ...item, id: this.nextId++ } as TranscriptItem] });
  }

  private notice(text: string, tone: "info" | "error" = "error"): void {
    this.push({ kind: "notice", text, tone });
  }

  /**
   * The agent message being written in this turn, creating it on first text,
   * tool, or permission question: the latest unfinished message since the
   * request.
   */
  private currentAgent(): Extract<TranscriptItem, { kind: "agent" }> {
    for (let index = this.state.transcript.length - 1; index >= 0; index--) {
      const item = this.state.transcript[index];
      if (item.kind === "user") break;
      if (item.kind === "agent" && !item.done) return item;
    }
    const item = { kind: "agent" as const, id: this.nextId++, text: "", done: false, tools: [], permissions: [] };
    this.set({ transcript: [...this.state.transcript, item] });
    return item;
  }

  private replace(item: TranscriptItem): void {
    this.set({ transcript: this.state.transcript.map((entry) => (entry.id === item.id ? item : entry)) });
  }

  private handle(event: AgentEvent): void {
    switch (event.type) {
      case "state":
        this.set({
          session: event.state,
          auth: event.state === "auth-required" ? event.auth : this.state.auth,
          ...(event.state === "crashed" || event.state === "closed" ? { busy: false } : {}),
        });
        if (event.state === "crashed") this.notice(event.message ?? "The agent stopped unexpectedly.");
        return;
      case "text": {
        if (event.kind !== "message") return;
        const agent = this.currentAgent();
        // Text after a tool call starts a new paragraph ("I'll check first.", tool, "Done.").
        const gap = agent.tools.length > (this.textTools.get(agent.id) ?? 0) && agent.text !== "" ? "\n\n" : "";
        this.textTools.set(agent.id, agent.tools.length);
        this.replace({ ...agent, text: agent.text + gap + event.text });
        return;
      }
      case "tool": {
        const agent = this.currentAgent();
        const existing = agent.tools.find((tool) => tool.id === event.id);
        const hasInput =
          event.input !== null && typeof event.input === "object" && Object.keys(event.input as object).length > 0;
        const tool: ToolItem = {
          id: event.id,
          title: event.title ?? existing?.title ?? null,
          status: event.status ?? existing?.status ?? null,
          input: hasInput ? event.input : (existing?.input ?? event.input ?? null),
          output: event.output ?? existing?.output ?? null,
        };
        const tools = existing ? agent.tools.map((item) => (item.id === event.id ? tool : item)) : [...agent.tools, tool];
        this.replace({ ...agent, tools });
        if (tool.status === "completed" && isWriteTool(tool.title)) this.onWrite?.();
        return;
      }
      case "permission": {
        // The question belongs to the answer being written, not after it.
        const agent = this.currentAgent();
        const ask: PermissionAsk = {
          requestId: event.requestId,
          toolCallId: event.toolCallId ?? null,
          title: event.title,
          options: event.options,
          answer: null,
        };
        this.replace({ ...agent, permissions: [...agent.permissions, ask] });
        return;
      }
      case "turn-end":
        this.finishTurn();
        return;
      case "install":
        this.set({ install: event.done >= event.total ? null : { providerId: event.providerId, done: event.done, total: event.total } });
        return;
      default:
        return;
    }
  }

  /** Mark this turn's agent message complete (it then renders as Markdown with its pages). */
  private finishTurn(): void {
    for (let index = this.state.transcript.length - 1; index >= 0; index--) {
      const item = this.state.transcript[index];
      if (item.kind === "user") return;
      if (item.kind === "agent" && !item.done) {
        // A question still open when the turn ends (Stop) was never answered.
        const permissions = item.permissions.map((ask) => (ask.answer === null ? { ...ask, answer: "cancelled" } : ask));
        this.replace({ ...item, done: true, permissions });
        return;
      }
    }
  }

  async refresh(): Promise<void> {
    if (this.bridge === null) return;
    try {
      const providers = await this.bridge.list();
      const chosen = providers.find((item) => item.id === this.state.providerId) ?? providers.find((item) => item.state === "ready") ?? providers[0] ?? null;
      this.set({ providers, providerId: chosen?.id ?? null, error: null });
    } catch (error) {
      this.set({ error: bridgeError(error) });
    }
  }

  choose(providerId: string): void {
    try {
      window.localStorage.setItem(PROVIDER_KEY, providerId);
    } catch {
      // Remembering the choice is a convenience only.
    }
    this.set({ providerId });
  }

  async install(providerId: string): Promise<void> {
    if (this.bridge === null) return;
    this.set({ install: { providerId, done: 0, total: 0 }, error: null });
    try {
      await this.bridge.installAdapter(providerId);
      this.set({ install: null });
      await this.refresh();
    } catch (error) {
      this.set({ install: null, error: bridgeError(error) });
    }
  }

  /** Start (or restart after sign-in) the chosen provider's session. */
  async start(): Promise<boolean> {
    if (this.bridge === null) return false;
    // A request can come from a page before the panel has listed the providers.
    if (this.state.providers === null) await this.refresh();
    const providerId = this.state.providerId;
    if (providerId === null) {
      this.set({ error: "Choose an agent first." });
      return false;
    }
    this.set({ session: "starting", auth: null, error: null });
    try {
      const { state } = await this.bridge.start(providerId);
      this.set({ sessionProvider: providerId, session: state as SessionState });
      return state === "ready";
    } catch (error) {
      this.set({ session: "none", sessionProvider: null, error: bridgeError(error) });
      return false;
    }
  }

  async restart(): Promise<void> {
    if (this.bridge === null) return;
    this.set({ auth: null, error: null });
    try {
      await this.bridge.restart();
    } catch (error) {
      this.set({ error: bridgeError(error) });
    }
  }

  private async ensureSession(): Promise<boolean> {
    if (this.state.session === "ready" && this.state.sessionProvider === this.state.providerId) return true;
    return this.start();
  }

  /** Send one request; the answer streams into the transcript. */
  async send(mode: AgentMode, request: string, context: AgentContext, label?: string): Promise<void> {
    if (this.bridge === null || request.trim() === "" || this.state.busy) return;
    this.push({ kind: "user", text: (label ?? request).trim(), mode });
    if (!(await this.ensureSession())) return;
    this.set({ busy: true });
    try {
      await this.bridge.prompt(buildPrompt(mode, request, context));
    } catch (error) {
      // A sign-in problem shows as the sign-in card (session state), not as an error too.
      if (this.state.session !== "auth-required") this.notice(bridgeError(error));
    } finally {
      this.finishTurn();
      this.set({ busy: false });
    }
  }

  /** Open the panel and send a request from elsewhere in the reader (e.g. the documentation check). */
  async sendFromPage(mode: AgentMode, request: string, context: AgentContext, label: string): Promise<void> {
    this.onOpen?.();
    await this.send(mode, request, context, label);
  }

  /** Draft a new page's title and body from one line; the agent writes nothing. */
  async compose(request: string, context: AgentContext): Promise<{ title: string; body: string } | null> {
    if (this.bridge === null || this.state.busy) return null;
    this.push({ kind: "user", text: `New page: ${request.trim()}`, mode: "ask" });
    if (!(await this.ensureSession())) return null;
    this.set({ busy: true });
    try {
      await this.bridge.prompt(composePrompt(request, context));
      const reply = [...this.state.transcript].reverse().find((item) => item.kind === "agent");
      return reply?.kind === "agent" ? parseComposed(reply.text) : null;
    } catch (error) {
      if (this.state.session !== "auth-required") this.notice(bridgeError(error));
      return null;
    } finally {
      this.finishTurn();
      this.set({ busy: false });
    }
  }

  async cancel(): Promise<void> {
    try {
      await this.bridge?.cancel();
    } catch (error) {
      this.set({ error: bridgeError(error) });
    }
  }

  /** Answer one of the agent's questions; `optionId` null refuses. */
  async answer(requestId: string, optionId: string | null): Promise<void> {
    const agent = this.state.transcript.find(
      (item): item is Extract<TranscriptItem, { kind: "agent" }> =>
        item.kind === "agent" && item.permissions.some((ask) => ask.requestId === requestId),
    );
    if (agent === undefined) return;
    const permissions = agent.permissions.map((ask) => {
      if (ask.requestId !== requestId) return ask;
      const kind = ask.options.find((candidate) => candidate.id === optionId)?.kind ?? "reject_once";
      const answer = kind === "allow_always" ? "allowed from now on" : kind.startsWith("allow") ? "allowed" : "refused";
      return { ...ask, answer };
    });
    this.replace({ ...agent, permissions });
    await this.bridge?.respondPermission(requestId, optionId);
  }

  /** Start over: a new conversation (the next request starts a new session). */
  async clear(): Promise<void> {
    await this.bridge?.close().catch(() => undefined);
    this.set({ transcript: [], session: "none", sessionProvider: null, auth: null, busy: false, error: null });
  }
}

export const agentStore = new AgentStore();

export function useAgent(): AgentState {
  return useSyncExternalStore(agentStore.subscribe, agentStore.snapshot);
}
