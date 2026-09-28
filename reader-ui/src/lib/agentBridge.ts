// The desktop app's in-app agent, as the reader sees it (issue #83). The
// Electron preload script exposes it as `window.kosDesktop.agent` to the
// reader UI only; in a plain browser (`kos-read`) there is no agent and the
// panel is not offered. The shapes mirror desktop/src/main/agents.

/** A provider as the desktop app lists it (AgentService.list). */
export interface AgentProviderInfo {
  id: string;
  displayName: string;
  state: "ready" | "not-installed" | "unsupported";
  version: string | null;
  message: string;
  adapterVersion: string;
  adapterInstalled: boolean;
}

export interface AuthHelp {
  message: string;
  command: string | null;
}

export type SessionState = "starting" | "ready" | "working" | "auth-required" | "crashed" | "closed";

/** One event from the shared ACP client (desktop/src/main/agents/acpSession.ts). */
export type AgentEvent =
  | { type: "state"; state: SessionState; message: string | null; auth: AuthHelp | null }
  | { type: "text"; kind: "message" | "thought"; text: string }
  | { type: "tool"; id: string; title: string | null; status: string | null; kind: string | null; input: unknown; output: unknown }
  | { type: "plan"; entries: { content: string; status: string }[] }
  | {
      type: "permission";
      requestId: string;
      toolCallId: string | null;
      title: string;
      options: { id: string; name: string; kind: string }[];
    }
  | { type: "turn-end"; stopReason: string }
  | { type: "install"; providerId: string; done: number; total: number };

export interface AgentBridge {
  list: () => Promise<AgentProviderInfo[]>;
  installAdapter: (providerId: string) => Promise<void>;
  start: (providerId: string) => Promise<{ state: string }>;
  prompt: (text: string) => Promise<string>;
  cancel: () => Promise<void>;
  respondPermission: (requestId: string, optionId: string | null) => Promise<boolean>;
  restart: () => Promise<void>;
  close: () => Promise<void>;
  onEvent: (callback: (event: AgentEvent) => void) => () => void;
}

interface DesktopBridge {
  agent?: AgentBridge;
  onReaderCommand?: (callback: (command: string) => void) => () => void;
}

function desktop(): DesktopBridge | null {
  return (window as { kosDesktop?: DesktopBridge }).kosDesktop ?? null;
}

/** The agent, or null outside the desktop app. */
export function agentBridge(): AgentBridge | null {
  return desktop()?.agent ?? null;
}

/** Menu commands the desktop app sends the reader ('new-page', 'toggle-agent'). */
export function onReaderCommand(callback: (command: string) => void): () => void {
  return desktop()?.onReaderCommand?.(callback) ?? (() => undefined);
}

/** An error from the main process, without Electron's "Error invoking remote method …" prefix. */
export function bridgeError(error: unknown): string {
  const text = error instanceof Error ? error.message : String(error);
  return text.replace(/^Error invoking remote method '[^']+': (?:\w*Error: )?/, "");
}
