import { describe, expect, it } from 'vitest'
import { parseCloneLine } from './cloneRunner'

describe('parseCloneLine', () => {
  it('reads progress events', () => {
    expect(
      parseCloneLine(
        '{"event": "progress", "line": "Receiving objects:  45% (9/20)", "percent": 45, "phase": "clone"}'
      )
    ).toEqual({
      event: 'progress',
      progress: { phase: 'clone', line: 'Receiving objects:  45% (9/20)', percent: 45 }
    })
    expect(
      parseCloneLine('{"event": "progress", "line": null, "percent": null, "phase": "index"}')
    ).toEqual({
      event: 'progress',
      progress: { phase: 'index', line: null, percent: null }
    })
  })

  it('reads the result and its lint issues', () => {
    expect(
      parseCloneLine(
        '{"event": "done", "index_error": null, "issues": [{"path": "knowledge/a.md", "message": "bad"}, 3], "name": "notes", "reindexed": false, "root": "C:\\\\kb\\\\notes"}'
      )
    ).toEqual({
      event: 'done',
      result: {
        ok: true,
        root: 'C:\\kb\\notes',
        name: 'notes',
        issues: [{ path: 'knowledge/a.md', message: 'bad' }],
        indexError: null
      }
    })
  })

  it('reads errors', () => {
    expect(
      parseCloneLine('{"detail": "Git could not sign in.", "error": "auth", "event": "error"}')
    ).toEqual({
      event: 'error',
      result: { ok: false, error: 'auth', detail: 'Git could not sign in.' }
    })
  })

  it('ignores anything else', () => {
    expect(parseCloneLine('')).toBeNull()
    expect(parseCloneLine('Cloning into ...')).toBeNull()
    expect(parseCloneLine('[1, 2]')).toBeNull()
    expect(parseCloneLine('{"event": "progress", "phase": "upload"}')).toBeNull()
    expect(parseCloneLine('{"event": "done"}')).toBeNull()
  })
})
