// The contract every in-app agent provider implements (issue #90, decision
// `in-app-agent-over-acp`).
//
// The app talks to coding agents over the Agent Client Protocol (ACP):
// JSON-RPC over the agent process's stdin and stdout. A provider says only
// what differs between agents: how to find the agent on this computer, how to
// start its ACP adapter, how to restrict it to the knowledge base's own MCP
// tools, how to explain its sign-in, and any small quirks of its adapter.
// Everything else (the process, the ACP session, streamed updates, and
// permission requests) belongs to the shared client in acpSession.ts, which
// never asks which agent it is talking to.
//
// A provider is done when it passes the conformance suite in
// testing/conformance.ts. Only Node built-ins and ACP types are imported, so
// providers are unit-testable outside Electron.

import type { AuthMethod, SessionNotification } from '@agentclientprotocol/sdk'

/** Whether the agent can be used on this computer, and why not. */
export interface ProviderStatus {
  /**
   * `ready`: found and usable. `not-installed`: the agent's own program is not
   * on this computer. `unsupported`: found but cannot be used (for example
   * this platform), with the reason in `message`.
   */
  state: 'ready' | 'not-installed' | 'unsupported'
  /** The agent's own executable the adapter will run, when found. */
  executable: string | null
  /** Its version as it reports it, when known. */
  version: string | null
  /** One sentence for a person: what was found, or what to do. */
  message: string
}

/** What the app hands a provider to start its adapter. */
export interface LaunchHost {
  /**
   * How to run a JavaScript file with Node: in the app, Electron's own binary
   * with ELECTRON_RUN_AS_NODE=1, so no separate Node or npx is needed.
   */
  node: { command: string; env: Record<string, string> }
  /** The absolute path of a file inside an installed package, e.g. an adapter's entry. */
  resolvePackageFile(packageName: string, file: string): string
  /** The environment the app runs in; a provider copies only what it needs to. */
  env: NodeJS.ProcessEnv
}

/** A process to spawn: the ACP adapter. */
export interface LaunchSpec {
  command: string
  args: string[]
  /** Added to the app's environment for this process. */
  env: Record<string, string>
}

/** How a person signs in when the agent says it needs to. */
export interface AuthHelp {
  /** One or two sentences in the app's words. */
  message: string
  /** A command to run in a terminal, when there is one (e.g. `claude /login`). */
  command: string | null
}

/** What the app may offer with this provider. */
export interface ProviderCapabilities {
  /** Continue an earlier session after a restart (`session/load`). */
  sessionResume: boolean
  /** Images in prompts. */
  images: boolean
}

/**
 * Small, pure corrections for one adapter's known quirks. Each hook is
 * optional; kandev keeps the same kind of per-agent "dialect".
 */
export interface ProviderDialect {
  /** Rewrite or drop (`null`) one session update before the app sees it. */
  normalizeUpdate?(notification: SessionNotification): SessionNotification | null
}

export interface AgentProvider {
  /** Stable id, e.g. `claude`. */
  readonly id: string
  /** The agent's name as people know it, e.g. `Claude Code`. */
  readonly displayName: string
  /**
   * The MCP client name the agent reports to `kos mcp`, under which its
   * writes appear ("Written by Claude Code in …"); see agent_identity.py.
   */
  readonly mcpClientName: string
  /** The ACP adapter shipped with the app, pinned to the version tested. */
  readonly adapter: { packageName: string; version: string; entry: string }
  readonly capabilities: ProviderCapabilities
  /** Find the agent on this computer. Never throws; a problem is a status. */
  detect(env: NodeJS.ProcessEnv, platform: NodeJS.Platform): Promise<ProviderStatus>
  /** The adapter process for a `ready` status. */
  launchSpec(status: ProviderStatus, host: LaunchHost): LaunchSpec
  /**
   * `_meta` for `session/new` (and `session/load`) that limits the agent to the
   * MCP servers it is given: no built-in file, shell, or web tools, and none
   * of the person's own MCP servers or hooks. Providers whose adapter takes
   * this through the environment instead return `undefined` and set it in
   * `launchSpec`.
   */
  sessionMeta(): Record<string, unknown> | undefined
  /** Explain the adapter's `authMethods` when a session needs sign-in. */
  authHelp(methods: readonly AuthMethod[]): AuthHelp
  readonly dialect?: ProviderDialect
}

/** The knowledge base's own MCP server, the only one a session gets. */
export interface KosMcpServer {
  command: string
  args: string[]
  env: Record<string, string>
}

/** The name the `kos` MCP server has inside every agent session. */
export const KOS_MCP_SERVER_NAME = 'knowledge-os'

/** What a place label reads as in provenance for writes from the app's own agent. */
export const IN_APP_PLACE = 'Knowledge OS app'
