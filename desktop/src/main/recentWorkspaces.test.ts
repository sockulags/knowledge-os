import { mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import type { RecentWorkspace } from '../shared/types'
import type { PathKind } from './reopen'
import {
  MAX_RECENT,
  addRecent,
  loadRecent,
  markMissing,
  removeRecent,
  saveRecent
} from './recentWorkspaces'

function entry(
  root: string,
  name = 'kb',
  lastOpened = '2026-09-22T10:00:00.000Z'
): RecentWorkspace {
  return { root, name, lastOpened }
}

describe('addRecent', () => {
  it('puts the newest entry first and removes its older duplicate', () => {
    const list = [entry('C:\\a'), entry('C:\\b')]
    expect(addRecent(list, entry('C:\\b', 'b2'), 'win32').map((item) => item.name)).toEqual([
      'b2',
      'kb'
    ])
  })

  it('treats Windows paths case- and separator-insensitively', () => {
    const list = [entry('C:\\Notes\\KB\\')]
    expect(addRecent(list, entry('c:/notes/kb'), 'win32')).toHaveLength(1)
  })

  it('keeps case-distinct paths apart on case-sensitive platforms', () => {
    expect(addRecent([entry('/notes/KB')], entry('/notes/kb'), 'linux')).toHaveLength(2)
  })

  it('caps the list', () => {
    let list: RecentWorkspace[] = []
    for (let i = 0; i < MAX_RECENT + 5; i++) list = addRecent(list, entry(`/kb/${i}`), 'linux')
    expect(list).toHaveLength(MAX_RECENT)
    expect(list[0].root).toBe(`/kb/${MAX_RECENT + 4}`)
  })
})

describe('removeRecent', () => {
  it('drops only the entry for that folder', () => {
    const list = [entry('C:\\a', 'a'), entry('C:\\b', 'b'), entry('C:\\c', 'c')]
    expect(removeRecent(list, 'C:\\b', 'win32').map((item) => item.name)).toEqual(['a', 'c'])
  })

  it('matches the folder the same way addRecent does', () => {
    expect(removeRecent([entry('C:\\Notes\\KB\\')], 'c:/notes/kb', 'win32')).toEqual([])
    expect(removeRecent([entry('/notes/KB')], '/notes/kb', 'linux')).toHaveLength(1)
  })

  it('leaves the list alone for a folder it does not have', () => {
    const list = [entry('/kb')]
    expect(removeRecent(list, '/other', 'linux')).toEqual(list)
  })
})

describe('markMissing', () => {
  it('marks entries whose folder is gone or is not a folder', () => {
    const kinds: Record<string, PathKind> = { '/here': 'directory', '/file': 'file' }
    const pathKind = (path: string): PathKind => kinds[path] ?? 'missing'
    const marked = markMissing([entry('/here'), entry('/gone'), entry('/file')], pathKind)
    expect(marked.map((item) => [item.root, item.missing])).toEqual([
      ['/here', false],
      ['/gone', true],
      ['/file', true]
    ])
    expect(marked[0]).toMatchObject(entry('/here'))
  })

  it('marks a deleted folder on disk, which can then be removed', () => {
    const dir = mkdtempSync(join(tmpdir(), 'kos-recent-'))
    const gone = join(dir, 'gone')
    try {
      const list = [entry(dir, 'here'), entry(gone, 'gone')]
      const pathKind = (path: string): PathKind => {
        try {
          return statSync(path).isDirectory() ? 'directory' : 'file'
        } catch {
          return 'missing'
        }
      }
      expect(markMissing(list, pathKind).map((item) => item.missing)).toEqual([false, true])
      expect(removeRecent(list, gone).map((item) => item.name)).toEqual(['here'])
    } finally {
      rmSync(dir, { recursive: true, force: true })
    }
  })
})

describe('loadRecent and saveRecent', () => {
  let dir: string
  let file: string

  beforeEach(() => {
    dir = mkdtempSync(join(tmpdir(), 'kos-recent-'))
    file = join(dir, 'nested', 'recent-workspaces.json')
  })

  afterEach(() => {
    rmSync(dir, { recursive: true, force: true })
  })

  it('round-trips the list through the user-data file', () => {
    const list = [entry('C:\\a', 'alpha'), entry('C:\\b', 'beta')]
    saveRecent(file, list)
    expect(loadRecent(file)).toEqual(list)
    expect(JSON.parse(readFileSync(file, 'utf-8')).version).toBe(1)
  })

  it('returns an empty list for a missing file', () => {
    expect(loadRecent(join(dir, 'missing.json'))).toEqual([])
  })

  it('returns an empty list for a damaged file', () => {
    const damaged = join(dir, 'damaged.json')
    writeFileSync(damaged, '{"workspaces": [', 'utf-8')
    expect(loadRecent(damaged)).toEqual([])
  })

  it('drops malformed entries and keeps the valid ones', () => {
    const mixed = join(dir, 'mixed.json')
    writeFileSync(
      mixed,
      JSON.stringify({
        version: 1,
        workspaces: [entry('C:\\ok'), { root: 3 }, null, { root: '' }]
      }),
      'utf-8'
    )
    expect(loadRecent(mixed)).toEqual([entry('C:\\ok')])
  })
})
