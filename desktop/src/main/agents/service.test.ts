import { mkdtempSync, rmSync } from 'fs'
import { tmpdir } from 'os'
import { dirname, join } from 'path'
import { fileURLToPath } from 'url'
import { afterEach, describe, expect, it } from 'vitest'
import type { AgentEvent } from './acpSession'
import type { AgentProvider } from './contract'
import { claudeProvider } from './providers/claude'
import { AgentService, electronLaunchHost, kosMcpCommand } from './service'
import { testHost } from './testing/conformance'
import { fakeRegistry } from './testing/tarball'

const MOCK_AGENT = join(dirname(fileURLToPath(import.meta.url)), 'testing', 'mockAgent.mjs')

// A tiny adapter "published" to an in-memory registry.
const registry = fakeRegistry('@acme/mock-acp', '1.0.0', {
  'node_modules/@acme/mock-acp': { 'package.json': '{}', 'dist/index.js': '' }
})

/** A provider whose adapter is the mock agent, to drive the service. */
const mockProvider: AgentProvider = {
  ...claudeProvider,
  adapter: registry.lock,
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
  const roots: string[] = []
  afterEach(() => {
    service?.close()
    while (roots.length > 0) rmSync(roots.pop()!, { recursive: true, force: true })
  })
  function adapters(): { root: string; fetchBytes: typeof registry.fetchBytes } {
    const root = mkdtempSync(join(tmpdir(), 'kos-service-'))
    roots.push(root)
    return { root, fetchBytes: registry.fetchBytes }
  }

  it('lists providers, runs one session at a time, and forwards its events', async () => {
    const events: AgentEvent[] = []
    service = new AgentService(
      testHost,
      adapters(),
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
    const context = { root: process.cwd(), kosMcp: kosMcpCommand('kos', {}, 'r.json') }
    // The adapter is installed on demand, before the first session.
    expect((await service.list())[0].adapterInstalled).toBe(false)
    await expect(service.start('mock', context)).rejects.toMatchObject({ kind: 'adapter-missing' })
    await service.installAdapter('mock')
    expect(events.filter((event) => event.type === 'install').at(-1)).toEqual({
      type: 'install',
      providerId: 'mock',
      done: 1,
      total: 1
    })
    expect((await service.list())[0].adapterInstalled).toBe(true)

    await service.start('mock', context)
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

  it('runs installed adapters with Electron as Node', async () => {
    const { root, fetchBytes } = adapters()
    const host = electronLaunchHost('/opt/app/knowledge-os', {}, root)
    expect(host.node).toEqual({
      command: '/opt/app/knowledge-os',
      env: { ELECTRON_RUN_AS_NODE: '1' }
    })
    expect(() => host.adapterEntry(registry.lock)).toThrow(/not installed/)
    await new AgentService(
      host,
      { root, fetchBytes },
      { name: 't', version: '0' },
      () => undefined,
      [mockProvider]
    ).installAdapter('mock')
    expect(host.adapterEntry(registry.lock)).toBe(
      join(root, 'mock-acp@1.0.0', 'node_modules', '@acme', 'mock-acp', 'dist', 'index.js')
    )
  })
})
