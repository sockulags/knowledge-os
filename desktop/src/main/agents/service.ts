// The in-app agent as the main process holds it: the providers on offer, at
// most one open session, and the session's events forwarded to the window.
// The panel that shows it is issue #83; this is what it will talk to over
// IPC. No 'electron' import, so it is unit-testable.

import { createRequire } from 'module'
import { dirname, join } from 'path'
import { AcpAgentSession, AgentSessionError, type AgentEvent } from './acpSession'
import { IN_APP_PLACE, type AgentProvider, type KosMcpServer, type LaunchHost } from './contract'
import { PROVIDERS } from './providers'

/** A provider as the panel lists it. */
export interface ProviderInfo {
  id: string
  displayName: string
  state: 'ready' | 'not-installed' | 'unsupported'
  version: string | null
  message: string
  adapterVersion: string
}

/** The open knowledge base, as a session needs it. */
export interface AgentContext {
  /** The knowledge base folder, the session's working directory. */
  root: string
  kosMcp: KosMcpServer
}

/**
 * How the app runs an adapter: Electron's own binary as Node
 * (ELECTRON_RUN_AS_NODE), reading the adapter straight from the app's asar
 * archive, which Electron-as-Node supports; no separate Node or npx.
 */
export function electronLaunchHost(execPath: string, env: NodeJS.ProcessEnv): LaunchHost {
  const requireHere = createRequire(__filename)
  return {
    node: { command: execPath, env: { ELECTRON_RUN_AS_NODE: '1' } },
    resolvePackageFile: (packageName, file) =>
      join(dirname(requireHere.resolve(`${packageName}/package.json`)), file),
    env
  }
}

/** `kos mcp` for the in-app agent: the same core the app runs, labelled as the app. */
export function kosMcpCommand(
  coreExecutable: string,
  env: NodeJS.ProcessEnv,
  runtimeFile: string
): KosMcpServer {
  const passed: Record<string, string> = { KOS_RUNTIME_FILE: runtimeFile }
  for (const name of ['PYTHONPATH', 'PYTHONUTF8', 'PYTHONIOENCODING', 'PYTHONUNBUFFERED']) {
    const value = env[name]
    if (value !== undefined) passed[name] = value
  }
  return {
    command: coreExecutable,
    args: ['-m', 'knowledge_os', 'mcp', '--place', IN_APP_PLACE],
    env: passed
  }
}

export class AgentService {
  private session: AcpAgentSession | null = null
  private providerId: string | null = null

  constructor(
    private readonly host: LaunchHost,
    private readonly clientInfo: { name: string; version: string },
    private readonly emit: (event: AgentEvent) => void,
    private readonly providers: readonly AgentProvider[] = PROVIDERS,
    private readonly platform: NodeJS.Platform = process.platform
  ) {}

  /** Every provider with what was found on this computer. */
  async list(): Promise<ProviderInfo[]> {
    return Promise.all(
      this.providers.map(async (provider) => {
        const status = await provider.detect(this.host.env, this.platform)
        return {
          id: provider.id,
          displayName: provider.displayName,
          state: status.state,
          version: status.version,
          message: status.message,
          adapterVersion: provider.adapter.version
        }
      })
    )
  }

  /** Open a session with one provider in the open knowledge base, closing any other. */
  async start(providerId: string, context: AgentContext): Promise<{ state: string }> {
    const provider = this.providers.find((candidate) => candidate.id === providerId)
    if (provider === undefined)
      throw new AgentSessionError('not-ready', `No agent called ${providerId}.`)
    this.close()
    const status = await provider.detect(this.host.env, this.platform)
    this.session = await AcpAgentSession.start({
      provider,
      status,
      host: this.host,
      cwd: context.root,
      kosMcp: context.kosMcp,
      clientInfo: this.clientInfo,
      onEvent: (event) => this.emit(event)
    })
    this.providerId = providerId
    return { state: this.session.state }
  }

  async prompt(text: string): Promise<string> {
    return this.require().prompt(text)
  }

  async cancel(): Promise<void> {
    return this.require().cancel()
  }

  respondPermission(requestId: string, optionId: string | null): boolean {
    return this.session?.respondPermission(requestId, optionId) ?? false
  }

  /** Start the adapter again, after a crash or once the person has signed in. */
  async restart(): Promise<void> {
    return this.require().restart()
  }

  /** The open session's provider, or null. */
  get current(): string | null {
    return this.session === null ? null : this.providerId
  }

  /** Stop the session, e.g. when the knowledge base closes. */
  close(): void {
    this.session?.close()
    this.session = null
    this.providerId = null
  }

  private require(): AcpAgentSession {
    if (this.session === null) throw new AgentSessionError('closed', 'No agent session is open.')
    return this.session
  }
}
