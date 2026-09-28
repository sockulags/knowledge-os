// The provider-independent conformance suite. Every provider in
// providers/index.ts runs it (conformance.test.ts); a new provider is done
// when it passes. It drives the shared ACP client with the provider's own
// launch environment, session `_meta`, dialect, and sign-in help against the
// scripted mock agent (mockAgent.mjs) instead of the real adapter, so it
// needs no agent installed and no network.

import { spawn } from 'child_process'
import { mkdtempSync, readFileSync, rmSync } from 'fs'
import { tmpdir } from 'os'
import { dirname, join } from 'path'
import { fileURLToPath } from 'url'
import { afterEach, describe, expect, it } from 'vitest'
import { AcpAgentSession, AgentSessionError, type AgentEvent } from '../acpSession'
import {
  KOS_MCP_SERVER_NAME,
  type AgentProvider,
  type LaunchHost,
  type ProviderStatus
} from '../contract'
import { checkLock, installFolderName } from '../installer'

const MOCK_AGENT = join(dirname(fileURLToPath(import.meta.url)), 'mockAgent.mjs')

/** A host whose adapters are "installed" at a fixed place; the suite runs the mock agent instead. */
export const testHost: LaunchHost = {
  node: { command: process.execPath, env: { MOCK_MARKER: 'host-node-env' } },
  adapterEntry: (adapter) => join('/adapters', installFolderName(adapter), adapter.entry),
  env: process.env
}

const READY: ProviderStatus = {
  state: 'ready',
  executable: '/opt/agent/bin/agent',
  version: '1.0.0',
  message: 'ready'
}

const KOS = {
  command: '/opt/kos/kos-core',
  args: ['-m', 'knowledge_os', 'mcp', '--place', 'Knowledge OS app'],
  env: { KOS_RUNTIME_FILE: '/tmp/runtime.json' }
}

interface Recorded {
  method: string
  params: Record<string, unknown>
  env: Record<string, string>
}

interface Harness {
  session: AcpAgentSession
  events: AgentEvent[]
  recorded: () => Recorded[]
  mockEnv: Record<string, string>
}

export function describeConformance(provider: AgentProvider): void {
  describe(`${provider.displayName} provider conformance`, () => {
    const cleanups: (() => void)[] = []
    // The answers the test gives, in order, to the permission questions it gets.
    let answers: (string | null)[] = []
    afterEach(() => {
      while (cleanups.length > 0) cleanups.pop()!()
      answers = []
    })

    async function open(mockEnv: Record<string, string> = {}): Promise<Harness> {
      const directory = mkdtempSync(join(tmpdir(), 'kos-acp-'))
      const recordFile = join(directory, 'record.jsonl')
      const events: AgentEvent[] = []
      const env = { MOCK_RECORD: recordFile, ...mockEnv }
      let session: AcpAgentSession | null = null
      cleanups.push(() => {
        session?.close()
        rmSync(directory, { recursive: true, force: true })
      })
      session = await AcpAgentSession.start({
        provider,
        status: READY,
        host: testHost,
        cwd: directory,
        kosMcp: KOS,
        clientInfo: { name: 'knowledge-os-desktop', version: 'test' },
        onEvent: (event) => {
          events.push(event)
          // Answer permission questions from the test through the recorded answer.
          if (event.type === 'permission' && answers.length > 0) {
            session!.respondPermission(event.requestId, answers.shift()!)
          }
        },
        spawnOverride: (spec) => {
          // The provider's own launch environment, the mock agent in place of its adapter.
          expect(spec.command).toBe(testHost.node.command)
          return spawn(process.execPath, [MOCK_AGENT], {
            env: { ...process.env, ...spec.env, ...env },
            stdio: ['pipe', 'pipe', 'pipe']
          })
        }
      })
      return {
        session,
        events,
        mockEnv: env,
        recorded: () =>
          readFileSync(recordFile, 'utf8')
            .trim()
            .split('\n')
            .filter(Boolean)
            .map((line) => JSON.parse(line) as Recorded)
      }
    }

    function text(events: AgentEvent[]): string {
      return events
        .filter(
          (event): event is Extract<AgentEvent, { type: 'text' }> =>
            event.type === 'text' && event.kind === 'message'
        )
        .map((event) => event.text)
        .join('')
    }

    it('launches its installed adapter with Node', () => {
      const spec = provider.launchSpec(READY, testHost)
      expect(spec.command).toBe(process.execPath)
      expect(spec.args).toEqual([testHost.adapterEntry(provider.adapter)])
      expect(spec.env['MOCK_MARKER']).toBe('host-node-env')
    })

    it('locks its adapter to exact, hashed npm packages without platform binaries', () => {
      const lock = provider.adapter
      expect(() => checkLock(lock)).not.toThrow()
      const paths = lock.packages.map((item) => item.path)
      expect(new Set(paths).size).toBe(paths.length)
      // The agents' own binaries are optional platform packages the adapter never needs.
      expect(paths.filter((path) => /-(linux|darwin|win32)-(x64|arm64)/.test(path))).toEqual([])
    })

    it('starts a session with kos mcp as the only MCP server and no file or terminal access', async () => {
      const { session, recorded } = await open()
      expect(session.state).toBe('ready')
      const init = recorded().find((entry) => entry.method === 'initialize')!
      const capabilities = init.params['clientCapabilities'] as {
        fs?: Record<string, boolean>
        terminal?: boolean
      }
      expect(capabilities.fs?.readTextFile ?? false).toBe(false)
      expect(capabilities.fs?.writeTextFile ?? false).toBe(false)
      expect(capabilities.terminal ?? false).toBe(false)
      const created = recorded().find((entry) => entry.method === 'session/new')!
      expect(created.params['mcpServers']).toEqual([
        {
          name: KOS_MCP_SERVER_NAME,
          command: KOS.command,
          args: KOS.args,
          env: [{ name: 'KOS_RUNTIME_FILE', value: '/tmp/runtime.json' }]
        }
      ])
      expect(created.params['_meta']).toEqual(provider.sessionMeta())
      // The adapter process gets the provider's launch environment.
      for (const [name, value] of Object.entries(provider.launchSpec(READY, testHost).env)) {
        if (name in created.env) expect(created.env[name]).toBe(value)
      }
    })

    it('streams the agent message and ends the turn', async () => {
      const { session, events } = await open()
      await expect(session.prompt('echo hello from the agent')).resolves.toBe('end_turn')
      expect(text(events)).toBe('hello from the agent')
      expect(events.at(-2)).toEqual({ type: 'turn-end', stopReason: 'end_turn' })
      expect(session.state).toBe('ready')
    })

    it('reports tool calls', async () => {
      const { session, events } = await open()
      await session.prompt('tool')
      const tools = events.filter((event) => event.type === 'tool')
      expect(tools.map((event) => event.type === 'tool' && event.status)).toEqual([
        'in_progress',
        'completed'
      ])
      expect(tools[0]).toMatchObject({ input: { query: 'retry' }, output: null })
      expect(tools[1]).toMatchObject({ output: '{"results":[]}' })
    })

    it('puts every permission question to the person', async () => {
      const { session, events } = await open()
      answers = ['allow']
      await session.prompt('permission')
      const question = events.find((event) => event.type === 'permission')
      expect(question).toMatchObject({ type: 'permission', title: 'write_note' })
      expect(text(events)).toBe('chose allow')

      answers = [null]
      await session.prompt('permission')
      expect(text(events)).toBe('chose allowchose nothing')
    })

    it('cancels a running turn', async () => {
      const { session } = await open()
      const turn = session.prompt('wait')
      await new Promise((resolve) => setTimeout(resolve, 100))
      await session.cancel()
      await expect(turn).resolves.toBe('cancelled')
    })

    it('reports a missing sign-in with its own help instead of failing', async () => {
      const { session, events } = await open({ MOCK_AUTH: 'required' })
      expect(session.state).toBe('auth-required')
      const state = events.find(
        (event) => event.type === 'state' && event.state === 'auth-required'
      )
      expect(state).toMatchObject({ auth: provider.authHelp([]) })
      await expect(session.prompt('echo hi')).rejects.toMatchObject({ kind: 'auth-required' })
    })

    it('reports a crashed agent and starts again', async () => {
      const { session, events } = await open({ MOCK_LOAD: '1' })
      const error = await session.prompt('crash').catch((caught: unknown) => caught)
      expect(error).toBeInstanceOf(AgentSessionError)
      expect((error as AgentSessionError).kind).toBe('crashed')
      expect(session.state).toBe('crashed')
      expect(events.some((event) => event.type === 'state' && event.state === 'crashed')).toBe(true)

      const before = session.id
      await session.restart()
      expect(session.state).toBe('ready')
      // Continues the same session where the provider and agent support it.
      if (provider.capabilities.sessionResume) expect(session.id).toBe(before)
      await expect(session.prompt('echo back again')).resolves.toBe('end_turn')
    })
  })
}
