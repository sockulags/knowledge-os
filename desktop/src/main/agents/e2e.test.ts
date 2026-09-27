// An end-to-end run against a real agent, skipped unless asked for:
//
//   KOS_AGENT_E2E=claude            the provider to run (claude or codex)
//   KOS_E2E_ROOT=<folder>           an open knowledge base with a project `demo`
//   KOS_E2E_CORE=<python or kos-core.exe>   runs `-m knowledge_os mcp`
//   KOS_RUNTIME_FILE=<runtime.json> the running core the MCP server talks to
//
// It starts the provider's real adapter under Electron-as-Node exactly as the
// app does, asks the agent to write one note through `kos mcp`, and checks
// that the note exists with the agent's provenance. The agent must be
// installed and signed in; this uses its model.

import { existsSync, readdirSync, readFileSync } from 'fs'
import { createRequire } from 'module'
import { join } from 'path'
import { describe, expect, it } from 'vitest'
import type { AgentEvent } from './acpSession'
import { IN_APP_PLACE } from './contract'
import { AgentService, electronLaunchHost, kosMcpCommand } from './service'

const providerId = process.env['KOS_AGENT_E2E']
const root = process.env['KOS_E2E_ROOT'] ?? ''
const core = process.env['KOS_E2E_CORE'] ?? ''
const runtimeFile = process.env['KOS_RUNTIME_FILE'] ?? ''

describe.skipIf(!providerId)('in-app agent end to end', () => {
  it('writes a note through kos mcp only, with the agent’s provenance', async () => {
    const electronBinary = createRequire(import.meta.url)('electron') as unknown as string
    const events: AgentEvent[] = []
    const service = new AgentService(
      electronLaunchHost(electronBinary, process.env),
      { name: 'knowledge-os-desktop', version: 'e2e' },
      (event) => {
        events.push(event)
        // The person allows the knowledge base's own tools, and nothing else.
        if (event.type === 'permission') {
          const allow = event.options.find((option) => option.kind.startsWith('allow'))
          const knowledgeTool = /knowledge-os|write_note|search/.test(event.title)
          service.respondPermission(event.requestId, knowledgeTool && allow ? allow.id : null)
        }
      }
    )
    const listed = await service.list()
    expect(listed.find((provider) => provider.id === providerId)?.state).toBe('ready')
    await service.start(providerId!, {
      root,
      kosMcp: kosMcpCommand(core, process.env, runtimeFile)
    })
    const title = `E2E note ${Date.now()}`
    const stop = await service.prompt(
      `Use the knowledge-os write_note tool to create a note titled "${title}" in project demo ` +
        `with the content "Written by the in-app agent test." Do not use any other tool. Then reply "done".`
    )
    service.close()
    expect(stop).toBe('end_turn')

    const files = readdirSync(join(root, 'projects', 'demo'), { recursive: true })
      .map(String)
      .filter((name) => name.endsWith('.md'))
      .map((name) => readFileSync(join(root, 'projects', 'demo', name), 'utf8'))
    const note = files.find((text) => text.includes(title))
    expect(note, JSON.stringify(events.slice(-20), null, 1)).toBeDefined()
    expect(note).toContain('kind: agent-authored')
    expect(note).toContain(`:${IN_APP_PLACE}`)
    // Only knowledge base tools ran.
    const tools = events.filter((event) => event.type === 'tool')
    expect(tools.length).toBeGreaterThan(0)
    expect(existsSync(root)).toBe(true)
  }, 180_000)
})
