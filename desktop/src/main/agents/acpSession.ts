// The shared ACP client: one agent process and one session, whatever the
// provider (see contract.ts).
//
// It starts the provider's adapter, runs `initialize` without offering any
// file or terminal capability, and opens a session whose only MCP server is
// the knowledge base's own `kos mcp`, with the provider's `_meta` limiting the
// agent to it. Prompts stream back as plain `AgentEvent`s. Every permission
// request is put to the person through `onEvent` and waits for
// `respondPermission`; nothing is approved automatically. When the agent says
// it needs sign-in, the session reports `auth-required` with the provider's
// own help instead of failing. A crashed process is reported, and `restart`
// starts a new one, continuing the same session when the provider supports
// `session/load`.

import { spawn, type ChildProcess } from 'child_process'
import { Readable, Writable } from 'stream'
import {
  ClientSideConnection,
  PROTOCOL_VERSION,
  ndJsonStream,
  type AuthMethod,
  type Client,
  type InitializeResponse,
  type McpServer,
  type RequestPermissionRequest,
  type RequestPermissionResponse,
  type SessionNotification,
  type StopReason
} from '@agentclientprotocol/sdk'
import {
  KOS_MCP_SERVER_NAME,
  type AgentProvider,
  type AuthHelp,
  type KosMcpServer,
  type LaunchHost,
  type ProviderStatus
} from './contract'

/** ACP's "authentication required" error code. */
const AUTH_REQUIRED = -32000
const STDERR_LIMIT = 8_000
/** How long a failed request waits to learn whether the process exited. */
const EXIT_GRACE_MS = 1_000

export type SessionState = 'starting' | 'ready' | 'working' | 'auth-required' | 'crashed' | 'closed'

/** Everything the app shows about a session, as plain data (safe for IPC). */
export type AgentEvent =
  | { type: 'state'; state: SessionState; message: string | null; auth: AuthHelp | null }
  | { type: 'text'; kind: 'message' | 'thought'; text: string }
  | {
      type: 'tool'
      id: string
      title: string | null
      status: string | null
      kind: string | null
      /** The tool's arguments, when the agent reports them (e.g. a page id to read). */
      input: unknown
      /** The tool's result as the agent reports it, once it has one. */
      output: unknown
    }
  | { type: 'plan'; entries: { content: string; status: string }[] }
  | {
      type: 'permission'
      requestId: string
      title: string
      options: { id: string; name: string; kind: string }[]
    }
  | { type: 'turn-end'; stopReason: StopReason }
  /** Installing a provider's adapter: `done` of `total` packages. */
  | { type: 'install'; providerId: string; done: number; total: number }

export interface SessionOptions {
  provider: AgentProvider
  status: ProviderStatus
  host: LaunchHost
  /** The session's working directory: the open knowledge base. */
  cwd: string
  /** How to run `kos mcp` for this knowledge base. */
  kosMcp: KosMcpServer
  onEvent: (event: AgentEvent) => void
  /** Name and version the app gives itself in `initialize`. */
  clientInfo: { name: string; version: string }
  /** For tests: spawn something else than `launchSpec` returns. */
  spawnOverride?: (spec: ReturnType<AgentProvider['launchSpec']>) => ChildProcess
}

export class AgentSessionError extends Error {
  constructor(
    readonly kind:
      'not-ready' | 'adapter-missing' | 'auth-required' | 'crashed' | 'protocol' | 'closed',
    message: string,
    readonly auth: AuthHelp | null = null
  ) {
    super(message)
    this.name = 'AgentSessionError'
  }
}

interface PendingPermission {
  resolve: (response: RequestPermissionResponse) => void
}

function isAuthRequired(error: unknown): boolean {
  return (
    typeof error === 'object' &&
    error !== null &&
    (error as { code?: unknown }).code === AUTH_REQUIRED
  )
}

function errorText(error: unknown): string {
  if (error instanceof Error) return error.message
  if (
    typeof error === 'object' &&
    error !== null &&
    typeof (error as { message?: unknown }).message === 'string'
  ) {
    return (error as { message: string }).message
  }
  return String(error)
}

/** The stdio MCP server entry for `kos mcp`. */
export function kosMcpServer(kos: KosMcpServer): McpServer {
  return {
    name: KOS_MCP_SERVER_NAME,
    command: kos.command,
    args: kos.args,
    env: Object.entries(kos.env).map(([name, value]) => ({ name, value }))
  }
}

export class AcpAgentSession {
  private child: ChildProcess | null = null
  private connection: ClientSideConnection | null = null
  private sessionId: string | null = null
  private initialized: InitializeResponse | null = null
  private stateValue: SessionState = 'starting'
  private stderrTail = ''
  private closing = false
  private permissions = new Map<string, PendingPermission>()
  private nextPermission = 1
  /** Settles when the current process exits. */
  private exitedSignal: Promise<void> = Promise.resolve()

  private constructor(private readonly options: SessionOptions) {}

  /** Start the adapter and open a session. Resolves once it is ready or needs sign-in. */
  static async start(options: SessionOptions): Promise<AcpAgentSession> {
    if (options.status.state !== 'ready') {
      throw new AgentSessionError('not-ready', options.status.message)
    }
    const session = new AcpAgentSession(options)
    await session.launch(null)
    return session
  }

  get state(): SessionState {
    return this.stateValue
  }

  /** The adapter's `initialize` answer (agent name, capabilities, auth methods). */
  get agentInfo(): InitializeResponse | null {
    return this.initialized
  }

  get id(): string | null {
    return this.sessionId
  }

  /** The last lines the adapter wrote to stderr, for a diagnostic. */
  get diagnostics(): string {
    return this.stderrTail
  }

  /** Send one prompt and wait for the turn to end; updates arrive through `onEvent`. */
  async prompt(text: string): Promise<StopReason> {
    const connection = this.requireReady()
    this.setState('working')
    try {
      const response = await connection.prompt({
        sessionId: this.sessionId!,
        prompt: [{ type: 'text', text }]
      })
      this.options.onEvent({ type: 'turn-end', stopReason: response.stopReason })
      if (this.stateValue === 'working') this.setState('ready')
      return response.stopReason
    } catch (error) {
      // A dying process fails the request before its exit event arrives.
      await Promise.race([
        this.exitedSignal,
        new Promise((resolve) => setTimeout(resolve, EXIT_GRACE_MS))
      ])
      if (this.stateValue === 'crashed' || this.stateValue === 'closed') {
        throw new AgentSessionError(
          this.stateValue === 'crashed' ? 'crashed' : 'closed',
          this.crashMessage()
        )
      }
      if (isAuthRequired(error)) {
        this.requireAuth()
        throw new AgentSessionError(
          'auth-required',
          'The agent needs you to sign in.',
          this.authHelp()
        )
      }
      this.setState('ready')
      throw new AgentSessionError('protocol', errorText(error))
    }
  }

  /** Stop the current turn; open permission questions are answered as cancelled. */
  async cancel(): Promise<void> {
    this.cancelPermissions()
    if (this.connection === null || this.sessionId === null) return
    await this.connection.cancel({ sessionId: this.sessionId })
  }

  /** Answer a permission question with one of its options, or `null` to refuse. */
  respondPermission(requestId: string, optionId: string | null): boolean {
    const pending = this.permissions.get(requestId)
    if (pending === undefined) return false
    this.permissions.delete(requestId)
    pending.resolve(
      optionId === null
        ? { outcome: { outcome: 'cancelled' } }
        : { outcome: { outcome: 'selected', optionId } }
    )
    return true
  }

  /**
   * Start a new adapter process after a crash or a sign-in. The same session
   * continues when the provider and adapter support `session/load`;
   * otherwise a new session starts.
   */
  async restart(): Promise<void> {
    const previous = this.sessionId
    this.stop()
    this.closing = false
    await this.launch(previous)
  }

  /** Stop the adapter process. */
  close(): void {
    this.stop()
    this.setState('closed')
  }

  // -- internals -------------------------------------------------------------

  private async launch(resumeId: string | null): Promise<void> {
    const { provider, status, host } = this.options
    this.setState('starting')
    const spec = provider.launchSpec(status, host)
    const child = this.options.spawnOverride
      ? this.options.spawnOverride(spec)
      : spawn(spec.command, spec.args, {
          cwd: this.options.cwd,
          env: { ...host.env, ...spec.env },
          stdio: ['pipe', 'pipe', 'pipe'],
          windowsHide: true
        })
    this.child = child
    this.stderrTail = ''
    child.stderr?.on('data', (chunk: Buffer) => {
      this.stderrTail = (this.stderrTail + chunk.toString()).slice(-STDERR_LIMIT)
    })
    const exited = new Promise<never>((_resolve, reject) => {
      const onExit = (): void => {
        if (this.child !== child) return
        this.connection = null
        this.cancelPermissions()
        if (!this.closing) this.setState('crashed', this.crashMessage())
        reject(new AgentSessionError('crashed', this.crashMessage()))
      }
      child.once('exit', onExit)
      child.once('error', onExit)
    })
    exited.catch(() => undefined)
    this.exitedSignal = exited.then(
      () => undefined,
      () => undefined
    )

    const stream = ndJsonStream(
      Writable.toWeb(child.stdin!) as WritableStream<Uint8Array>,
      Readable.toWeb(child.stdout!) as ReadableStream<Uint8Array>
    )
    // The deprecated class is the SDK's plain request/response client; the
    // newer builder API scopes a connection to one callback, which does not
    // fit a session that lives as long as the panel is open.
    const connection = new ClientSideConnection(() => this.client(), stream)
    this.connection = connection

    try {
      this.initialized = await Promise.race([
        connection.initialize({
          protocolVersion: PROTOCOL_VERSION,
          // No file system or terminal: the agent reaches the knowledge base
          // only through `kos mcp`, like any external agent.
          clientCapabilities: {},
          clientInfo: this.options.clientInfo
        }),
        exited
      ])
      const meta = provider.sessionMeta()
      const mcpServers = [kosMcpServer(this.options.kosMcp)]
      if (
        resumeId !== null &&
        provider.capabilities.sessionResume &&
        this.initialized.agentCapabilities?.loadSession
      ) {
        await Promise.race([
          connection.loadSession({
            sessionId: resumeId,
            cwd: this.options.cwd,
            mcpServers,
            ...(meta ? { _meta: meta } : {})
          }),
          exited
        ])
        this.sessionId = resumeId
      } else {
        const created = await Promise.race([
          connection.newSession({
            cwd: this.options.cwd,
            mcpServers,
            ...(meta ? { _meta: meta } : {})
          }),
          exited
        ])
        this.sessionId = created.sessionId
      }
      this.setState('ready')
    } catch (error) {
      if (error instanceof AgentSessionError) throw error
      if (isAuthRequired(error)) {
        this.requireAuth()
        return
      }
      this.stop()
      this.setState('crashed', errorText(error))
      throw new AgentSessionError('protocol', errorText(error))
    }
  }

  private client(): Client {
    return {
      requestPermission: (params) => this.askPermission(params),
      sessionUpdate: async (notification) => this.forward(notification)
    }
  }

  private askPermission(params: RequestPermissionRequest): Promise<RequestPermissionResponse> {
    const requestId = `permission-${this.nextPermission++}`
    return new Promise((resolve) => {
      this.permissions.set(requestId, { resolve })
      this.options.onEvent({
        type: 'permission',
        requestId,
        title: params.toolCall.title ?? 'The agent asks to use a tool',
        options: params.options.map((option) => ({
          id: option.optionId,
          name: option.name,
          kind: option.kind
        }))
      })
    })
  }

  private forward(notification: SessionNotification): void {
    const normalize = this.options.provider.dialect?.normalizeUpdate
    const update = (normalize ? normalize(notification) : notification)?.update
    if (update === undefined) return
    switch (update.sessionUpdate) {
      case 'agent_message_chunk':
      case 'agent_thought_chunk':
        if (update.content.type === 'text') {
          this.options.onEvent({
            type: 'text',
            kind: update.sessionUpdate === 'agent_message_chunk' ? 'message' : 'thought',
            text: update.content.text
          })
        }
        return
      case 'tool_call':
      case 'tool_call_update':
        this.options.onEvent({
          type: 'tool',
          id: update.toolCallId,
          title: update.title ?? null,
          status: update.status ?? null,
          kind: update.kind ?? null,
          input: update.rawInput ?? null,
          output: update.rawOutput ?? null
        })
        return
      case 'plan':
        this.options.onEvent({
          type: 'plan',
          entries: update.entries.map((entry) => ({ content: entry.content, status: entry.status }))
        })
        return
      default:
        return
    }
  }

  private authHelp(): AuthHelp {
    return this.options.provider.authHelp((this.initialized?.authMethods ?? []) as AuthMethod[])
  }

  private requireAuth(): void {
    const help = this.authHelp()
    this.stateValue = 'auth-required'
    this.options.onEvent({
      type: 'state',
      state: 'auth-required',
      message: help.message,
      auth: help
    })
  }

  private requireReady(): ClientSideConnection {
    if (this.connection === null || this.sessionId === null || this.stateValue !== 'ready') {
      const kind =
        this.stateValue === 'auth-required'
          ? 'auth-required'
          : this.stateValue === 'crashed'
            ? 'crashed'
            : 'closed'
      throw new AgentSessionError(
        kind,
        `The agent is not ready (${this.stateValue}).`,
        kind === 'auth-required' ? this.authHelp() : null
      )
    }
    return this.connection
  }

  private setState(state: SessionState, message: string | null = null): void {
    this.stateValue = state
    this.options.onEvent({ type: 'state', state, message, auth: null })
  }

  private crashMessage(): string {
    const tail = this.stderrTail.trim().split('\n').slice(-3).join('\n')
    return tail ? `The agent stopped unexpectedly: ${tail}` : 'The agent stopped unexpectedly.'
  }

  private cancelPermissions(): void {
    for (const pending of this.permissions.values())
      pending.resolve({ outcome: { outcome: 'cancelled' } })
    this.permissions.clear()
  }

  private stop(): void {
    this.closing = true
    this.cancelPermissions()
    const child = this.child
    this.child = null
    this.connection = null
    if (child !== null && child.exitCode === null && !child.killed) child.kill()
  }
}
