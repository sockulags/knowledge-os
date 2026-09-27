// Claude Code through @agentclientprotocol/claude-agent-acp, which wraps the
// Claude Agent SDK and reuses the Claude Code login already on this computer.
//
// The adapter is installed on demand from its lock (the app does not ship
// Anthropic's proprietary SDK), without the SDK's optional platform binary of
// about 200 MB: the adapter runs the person's own `claude` instead
// (CLAUDE_CODE_EXECUTABLE). On Windows the native `claude.exe` is preferred
// over an npm `claude.cmd` shim.

import type { AuthMethod } from '@agentclientprotocol/sdk'
import type { AgentProvider, AuthHelp, LaunchHost, LaunchSpec, ProviderStatus } from '../contract'
import { findOnPath, probeVersion } from '../detect'
import type { AdapterLock } from '../installer'
import claudeLock from '../adapters/claude-agent-acp.lock.json'

/** Installed on demand; regenerate with scripts/lock-adapter.mjs. */
export const CLAUDE_ADAPTER: AdapterLock = claudeLock

export const claudeProvider: AgentProvider = {
  id: 'claude',
  displayName: 'Claude Code',
  mcpClientName: 'claude-code',
  adapter: CLAUDE_ADAPTER,
  capabilities: { sessionResume: true, images: true },

  async detect(env, platform): Promise<ProviderStatus> {
    const explicit = env['CLAUDE_CODE_EXECUTABLE']?.trim()
    const executable = explicit || findOnPath('claude', { env, platform })
    if (!executable) {
      return {
        state: 'not-installed',
        executable: null,
        version: null,
        message:
          'Claude Code is not installed on this computer. Install it from claude.com/claude-code, sign in with `claude`, then try again.'
      }
    }
    const version = await probeVersion(executable, env)
    return {
      state: 'ready',
      executable,
      version,
      message: version ? `Claude Code ${version}` : 'Claude Code'
    }
  },

  launchSpec(status: ProviderStatus, host: LaunchHost): LaunchSpec {
    return {
      command: host.node.command,
      args: [host.adapterEntry(CLAUDE_ADAPTER)],
      env: {
        ...host.node.env,
        ...(status.executable ? { CLAUDE_CODE_EXECUTABLE: status.executable } : {})
      }
    }
  },

  sessionMeta(): Record<string, unknown> {
    return {
      claudeCode: {
        options: {
          // No built-in tools (files, shell, web): only the MCP servers the
          // session is given, which is kos mcp alone.
          tools: [],
          // Ignore the person's own MCP servers, hooks, and settings files,
          // so nothing but kos mcp reaches the session.
          strictMcpConfig: true,
          settingSources: [],
          // Never offer Claude Code's mode that skips permission questions:
          // every question goes to the person.
          allowDangerouslySkipPermissions: false
        }
      }
    }
  },

  authHelp(methods: readonly AuthMethod[]): AuthHelp {
    const terminal = methods.find((method) => method.id === 'claude-login')
    return {
      message: terminal
        ? 'Claude Code is not signed in. Run `claude /login` in a terminal, then start the agent again.'
        : 'Claude Code is not signed in. Open a terminal, run `claude`, sign in with /login, then start the agent again.',
      command: 'claude /login'
    }
  }
}
