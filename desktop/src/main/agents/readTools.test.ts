import { readFileSync } from 'fs'
import { dirname, join } from 'path'
import { fileURLToPath } from 'url'
import { describe, expect, it } from 'vitest'
import { KOS_READ_TOOLS, isKosReadTool, kosToolName } from './acpSession'

const TOOLS_PY = join(
  dirname(fileURLToPath(import.meta.url)),
  '../../../../knowledge_os/agent_access/tools.py'
)

/** Every `ToolSpec(name=..., read_only=...)` in the Python tool registry. */
function pythonTools(): Map<string, boolean> {
  const source = readFileSync(TOOLS_PY, 'utf8')
  const tools = new Map<string, boolean>()
  for (const block of source.split(/\bToolSpec\(/).slice(1)) {
    const name = /^\s*name="([a-z_]+)"/.exec(block)?.[1]
    const readOnly = /\bread_only=(True|False)\b/.exec(block)?.[1]
    if (name !== undefined && readOnly !== undefined) tools.set(name, readOnly === 'True')
  }
  return tools
}

describe('KOS_READ_TOOLS', () => {
  it('lists exactly the tools tools.py marks read_only=True', () => {
    const tools = pythonTools()
    // A parse that finds nothing would pass trivially.
    expect(tools.size).toBeGreaterThanOrEqual(10)
    const readOnly = [...tools].filter(([, value]) => value).map(([name]) => name)
    expect([...KOS_READ_TOOLS].sort()).toEqual(readOnly.sort())
  })
})

describe('kosToolName', () => {
  it('reads the tool from each adapter’s title', () => {
    expect(kosToolName({ title: 'mcp__knowledge-os__read_page' })).toBe('read_page')
    expect(kosToolName({ title: 'mcp.knowledge-os.read_page' })).toBe('read_page')
    expect(kosToolName({ title: 'knowledge-os/read_page' })).toBe('read_page')
  })

  it('takes the structured fields when there is no title', () => {
    expect(kosToolName({ _meta: { claudeCode: { toolName: 'mcp__knowledge-os__search' } } })).toBe(
      'search'
    )
  })

  it('knows nothing from a call that names no tool', () => {
    expect(kosToolName({})).toBeNull()
    expect(kosToolName({ title: '  ' })).toBeNull()
    // The arguments are the model's to choose, so they alone name nothing.
    expect(
      kosToolName({ rawInput: { server: 'knowledge-os', tool: 'read_page', arguments: {} } })
    ).toBeNull()
  })

  it('refuses a call whose fields disagree or name another server', () => {
    expect(
      kosToolName({
        title: 'mcp__knowledge-os__read_page',
        _meta: { claudeCode: { toolName: 'mcp__knowledge-os__write_note' } }
      })
    ).toBeNull()
    expect(
      kosToolName({
        title: 'mcp__knowledge-os__read_page',
        _meta: { claudeCode: { mcpServer: { name: 'other', source: 'config' } } }
      })
    ).toBeNull()
    expect(
      kosToolName({
        title: 'mcp.knowledge-os.read_page',
        rawInput: { server: 'knowledge-os', tool: 'write_note', arguments: {} }
      })
    ).toBeNull()
    expect(kosToolName({ title: 'mcp.other.read_page' })).toBeNull()
    expect(kosToolName({ title: 'mcpXknowledge-os.read_page' })).toBeNull()
  })

  it('lets only read tools run without asking', () => {
    expect(isKosReadTool({ title: 'mcp.knowledge-os.list_folder' })).toBe(true)
    expect(isKosReadTool({ title: 'mcp__knowledge-os__write_note' })).toBe(false)
    expect(isKosReadTool({ title: 'Bash' })).toBe(false)
  })
})
