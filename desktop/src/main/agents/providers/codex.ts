// Codex through @agentclientprotocol/codex-acp, which runs `codex app-server`
// and reuses the Codex login (ChatGPT or API key) already on this computer.
//
// The adapter is installed on demand from its lock, without the platform
// binary of several hundred MB that its @openai/codex dependency would bring:
// the adapter runs the person's own `codex` instead (CODEX_PATH).
//
// Codex has no switch that removes its built-in tools. The session starts in
// codex-acp's `read-only` mode, so editing files or reaching the network needs
// a permission the person grants in the app; reading files in the workspace
// stays possible, and MCP servers in the person's own ~/.codex/config.toml
// also load. That is weaker than the Claude provider and is documented.

import type { AgentProvider, AuthHelp, LaunchHost, LaunchSpec, ProviderStatus } from '../contract'
import { findOnPath, probeVersion } from '../detect'
import type { AdapterLock } from '../installer'
import codexLock from '../adapters/codex-acp.lock.json'

/** Installed on demand; regenerate with scripts/lock-adapter.mjs. */
export const CODEX_ADAPTER: AdapterLock = codexLock

export const codexProvider: AgentProvider = {
  id: 'codex',
  displayName: 'Codex',
  mcpClientName: 'codex-mcp-client',
  adapter: CODEX_ADAPTER,
  capabilities: { sessionResume: true, images: true },

  async detect(env, platform): Promise<ProviderStatus> {
    const explicit = env['CODEX_PATH']?.trim()
    const executable = explicit || findOnPath('codex', { env, platform })
    if (!executable) {
      return {
        state: 'not-installed',
        executable: null,
        version: null,
        message:
          'Codex is not installed on this computer. Install it with `npm install -g @openai/codex`, sign in with `codex login`, then try again.'
      }
    }
    const version = await probeVersion(executable, env)
    return { state: 'ready', executable, version, message: version ?? 'Codex' }
  },

  launchSpec(status: ProviderStatus, host: LaunchHost): LaunchSpec {
    return {
      command: host.node.command,
      args: [host.adapterEntry(CODEX_ADAPTER)],
      env: {
        ...host.node.env,
        ...(status.executable ? { CODEX_PATH: status.executable } : {}),
        // Edits and network access need the person's permission.
        INITIAL_AGENT_MODE: 'read-only'
      }
    }
  },

  sessionMeta(): undefined {
    return undefined
  },

  // Codex offers ChatGPT and API-key sign-in; both start with `codex login`.
  authHelp(): AuthHelp {
    return {
      message:
        'Codex is not signed in. Run `codex login` in a terminal, then start the agent again.',
      command: 'codex login'
    }
  }
}
