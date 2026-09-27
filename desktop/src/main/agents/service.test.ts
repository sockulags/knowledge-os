import { dirname, join } from 'path'
import { fileURLToPath } from 'url'
import { afterEach, describe, expect, it } from 'vitest'
import type { AgentEvent } from './acpSession'
import type { AgentProvider } from './contract'
import { claudeProvider } from './providers/claude'
import { AgentService, electronLaunchHost, kosMcpCommand } from './service'
import { testHost } from './testing/conformance'

const MOCK_AGENT = join(dirname(fileURLToPath(import.meta.url)), 'testing', 'mockAgent.mjs')

/** A provider whose adapter is the mock agent, to drive the service. */
const mockProvider: AgentProvider = {
  ...claudeProvider,
  id: 'mock',
  displayName: 'Mock',
  detect: async () => ({
    state: 'ready',
    executable: null,
    version: '1.0.0',
    message: 'Mock 1.0.0'
  }),
  launchSpec: () => ({ command: process.execPath, args: [MOCK_AGENT], env: {} })
}
const missingProvider: AgentProvider = {
  ...mockProvider,
  id: 'missing',
  detect: async () => ({
    state: 'not-installed',
    executable: null,
    version: null,
    message: 'Not here.'
  })
}

describe('AgentService', () => {
  let service: AgentService | null = null
  afterEach(() => service?.close())

  it('lists providers, runs one session at a time, and forwards its events', async () => {
    const events: AgentEvent[] = []
    service = new AgentService(
      testHost,
      { name: 'test', version: '0' },
      (event) => events.push(event),
      [mockProvider, missingProvider]
    )
    expect((await service.list()).map((provider) => [provider.id, provider.state])).toEqual([
      ['mock', 'ready'],
      ['missing', 'not-installed']
    ])
    await expect(
      service.start('missing', { root: process.cwd(), kosMcp: kosMcpCommand('kos', {}, 'r.json') })
    ).rejects.toMatchObject({
      kind: 'not-ready',
      message: 'Not here.'
    })
    await service.start('mock', { root: process.cwd(), kosMcp: kosMcpCommand('kos', {}, 'r.json') })
    expect(service.current).toBe('mock')
    await expect(service.prompt('echo hi')).resolves.toBe('end_turn')
    expect(events.some((event) => event.type === 'text' && event.text === 'hi')).toBe(true)
    service.close()
    expect(service.current).toBeNull()
    await expect(service.prompt('echo hi')).rejects.toMatchObject({ kind: 'closed' })
  })

  it('runs kos mcp from the app’s own core, labelled as the app', () => {
    const kos = kosMcpCommand(
      '/app/core/kos-core.exe',
      { PYTHONPATH: '/repo', HOME: '/home/me' },
      '/data/runtime.json'
    )
    expect(kos).toEqual({
      command: '/app/core/kos-core.exe',
      args: ['-m', 'knowledge_os', 'mcp', '--place', 'Knowledge OS app'],
      env: { KOS_RUNTIME_FILE: '/data/runtime.json', PYTHONPATH: '/repo' }
    })
  })

  it('runs adapters with Electron as Node from the installed packages', () => {
    const host = electronLaunchHost('/opt/app/knowledge-os', {})
    expect(host.node).toEqual({
      command: '/opt/app/knowledge-os',
      env: { ELECTRON_RUN_AS_NODE: '1' }
    })
    expect(
      host.resolvePackageFile('@agentclientprotocol/claude-agent-acp', 'dist/index.js')
    ).toMatch(/@agentclientprotocol[\\/]claude-agent-acp[\\/]dist[\\/]index\.js$/)
  })
})
