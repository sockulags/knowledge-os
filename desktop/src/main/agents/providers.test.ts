import { chmodSync, mkdtempSync, rmSync, writeFileSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'
import { afterEach, describe, expect, it } from 'vitest'
import { findOnPath } from './detect'
import { claudeProvider } from './providers/claude'
import { codexProvider } from './providers/codex'
import { PROVIDERS, findProvider } from './providers'
import { testHost } from './testing/conformance'

const directories: string[] = []
afterEach(() => {
  while (directories.length > 0) rmSync(directories.pop()!, { recursive: true, force: true })
})

/** A folder with a fake agent program that prints `version` for --version. */
function fakeAgent(name: string, version: string): string {
  const directory = mkdtempSync(join(tmpdir(), 'kos-agent-'))
  directories.push(directory)
  const file = join(directory, name)
  writeFileSync(file, `#!/bin/sh\necho "${version}"\n`)
  chmodSync(file, 0o755)
  return directory
}

describe('findOnPath', () => {
  it('prefers a native .exe over an npm .cmd shim in the same folder on Windows', () => {
    const files = new Set([
      'C:\\tools\\claude.cmd',
      'C:\\tools\\claude.exe',
      'C:\\later\\claude.exe'
    ])
    const found = findOnPath('claude', {
      env: { Path: 'C:\\tools;C:\\later' },
      platform: 'win32',
      isFile: (path) => files.has(path.replace(/\//g, '\\'))
    })
    expect(found?.replace(/\//g, '\\')).toBe('C:\\tools\\claude.exe')
  })

  it('returns null when the program is not on PATH', () => {
    expect(
      findOnPath('claude', { env: { PATH: '/nowhere' }, platform: 'linux', isFile: () => false })
    ).toBeNull()
  })
})

describe.skipIf(process.platform === 'win32')('detect', () => {
  it('finds Claude Code on PATH with its version', async () => {
    const directory = fakeAgent('claude', '2.1.0 (Claude Code)')
    const status = await claudeProvider.detect({ PATH: directory }, process.platform)
    expect(status).toMatchObject({
      state: 'ready',
      executable: join(directory, 'claude'),
      version: '2.1.0 (Claude Code)'
    })
  })

  it('says how to install an agent that is missing', async () => {
    for (const provider of PROVIDERS) {
      const status = await provider.detect({ PATH: '/nowhere' }, process.platform)
      expect(status.state).toBe('not-installed')
      expect(status.message).toMatch(/not installed/)
    }
  })

  it('honours an explicit executable', async () => {
    const directory = fakeAgent('my-codex', 'codex-cli 0.156.1')
    const status = await codexProvider.detect(
      { PATH: '/nowhere', CODEX_PATH: join(directory, 'my-codex') },
      process.platform
    )
    expect(status).toMatchObject({ state: 'ready', version: 'codex-cli 0.156.1' })
  })
})

describe('launch and session options', () => {
  const ready = {
    state: 'ready' as const,
    executable: '/usr/local/bin/agent',
    version: null,
    message: ''
  }

  it('points the Claude adapter at the person’s own claude and turns off everything but the given MCP servers', () => {
    expect(claudeProvider.launchSpec(ready, testHost).env['CLAUDE_CODE_EXECUTABLE']).toBe(
      '/usr/local/bin/agent'
    )
    expect(claudeProvider.sessionMeta()).toEqual({
      claudeCode: {
        options: {
          tools: [],
          strictMcpConfig: true,
          settingSources: [],
          allowDangerouslySkipPermissions: false
        }
      }
    })
    expect(claudeProvider.authHelp([]).command).toBe('claude /login')
  })

  it('points the Codex adapter at the person’s own codex in read-only mode', () => {
    const env = codexProvider.launchSpec(ready, testHost).env
    expect(env['CODEX_PATH']).toBe('/usr/local/bin/agent')
    expect(env['INITIAL_AGENT_MODE']).toBe('read-only')
    expect(codexProvider.authHelp([]).command).toBe('codex login')
  })

  it('finds providers by id', () => {
    expect(findProvider('claude')).toBe(claudeProvider)
    expect(findProvider('nope')).toBeNull()
    expect(new Set(PROVIDERS.map((provider) => provider.id)).size).toBe(PROVIDERS.length)
  })
})
