// The in-app agent as the main process holds it: the providers on offer, at
// most one open session, and the session's events forwarded to the window.
// The panel that shows it is issue #83; this is what it will talk to over
// IPC. No 'electron' import, so it is unit-testable.

import { AcpAgentSession, AgentSessionError, type AgentEvent } from './acpSession'
import { IN_APP_PLACE, type AgentProvider, type KosMcpServer, type LaunchHost } from './contract'
import { installAdapter, installedEntry, type FetchBytes } from './installer'
import { PROVIDERS } from './providers'

/** A provider as the panel lists it. */
export interface ProviderInfo {
  id: string
  displayName: string
  state: 'ready' | 'not-installed' | 'unsupported'
  version: string | null
  message: string
  adapterVersion: string
  /** Whether its adapter is installed; `installAdapter` fetches it. */
  adapterInstalled: boolean
}

/** The open knowledge base, as a session needs it. */
export interface AgentContext {
  /** The knowledge base folder, the session's working directory. */
  root: string
  kosMcp: KosMcpServer
}

/**
 * How the app runs an adapter: Electron's own binary as Node
 * (ELECTRON_RUN_AS_NODE), so no separate Node or npx, from the adapter
 * installed on demand under `adaptersRoot` (see installer.ts).
 */
export function electronLaunchHost(
  execPath: string,
  env: NodeJS.ProcessEnv,
  adaptersRoot: string
): LaunchHost {
  return {
    node: { command: execPath, env: { ELECTRON_RUN_AS_NODE: '1' } },
    adapterEntry: (adapter) => {
      const entry = installedEntry(adapter, adaptersRoot)
      if (entry === null) {
        throw new AgentSessionError('adapter-missing', `${adapter.packageName} is not installed.`)
      }
      return entry
    },
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
    // -P: the agent's working folder is the knowledge base, which must never
    // shadow the knowledge_os package (`python -m` would import it from there).
    args: ['-P', '-m', 'knowledge_os', 'mcp', '--place', IN_APP_PLACE],
    env: passed
  }
}

export class AgentService {
  private session: AcpAgentSession | null = null
  private providerId: string | null = null

  constructor(
    private readonly host: LaunchHost,
    /** Where adapters are installed, and how their packages are downloaded. */
    private readonly adapters: { root: string; fetchBytes: FetchBytes },
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
          adapterVersion: provider.adapter.version,
          adapterInstalled: installedEntry(provider.adapter, this.adapters.root) !== null
        }
      })
    )
  }

  /**
   * Fetch a provider's adapter at the exact version tested, checking every
   * package's hash; progress arrives as `install` events. A running session
   * of that provider is closed first, since an update replaces its files.
   */
  async installAdapter(providerId: string): Promise<void> {
    const provider = this.find(providerId)
    if (this.providerId === providerId) this.close()
    await installAdapter(
      provider.adapter,
      this.adapters.root,
      this.adapters.fetchBytes,
      ({ done, total }) => this.emit({ type: 'install', providerId, done, total })
    )
  }

  /** Open a session with one provider in the open knowledge base, closing any other. */
  async start(providerId: string, context: AgentContext): Promise<{ state: string }> {
    const provider = this.find(providerId)
    // The agent itself first: installing its adapter does not help without it.
    const status = await provider.detect(this.host.env, this.platform)
    if (status.state !== 'ready') throw new AgentSessionError('not-ready', status.message)
    if (installedEntry(provider.adapter, this.adapters.root) === null) {
      throw new AgentSessionError(
        'adapter-missing',
        `${provider.displayName} needs its adapter (${provider.adapter.packageName} ${provider.adapter.version}) installed first.`
      )
    }
    this.close()
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

  private find(providerId: string): AgentProvider {
    const provider = this.providers.find((candidate) => candidate.id === providerId)
    if (provider === undefined)
      throw new AgentSessionError('not-ready', `No agent called ${providerId}.`)
    return provider
  }

  private require(): AcpAgentSession {
    if (this.session === null) throw new AgentSessionError('closed', 'No agent session is open.')
    return this.session
  }
}
