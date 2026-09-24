import { mkdirSync, mkdtempSync, rmSync, statSync, writeFileSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import type { RecentWorkspace } from '../shared/types'
import { decideStartup, WORKSPACE_MARKER, type PathKind } from './reopen'

function pathKind(path: string): PathKind {
  try {
    return statSync(path).isDirectory() ? 'directory' : 'file'
  } catch {
    return 'missing'
  }
}

describe('decideStartup', () => {
  let dir: string
  let kb: string
  let recent: RecentWorkspace[]

  beforeEach(() => {
    dir = mkdtempSync(join(tmpdir(), 'kos-reopen-'))
    kb = join(dir, 'notes')
    mkdirSync(kb)
    writeFileSync(join(kb, WORKSPACE_MARKER), '[workspace]\nversion = 1\n', 'utf-8')
    recent = [
      { root: kb, name: 'My notes', lastOpened: '2026-09-24T08:00:00.000Z' },
      { root: join(dir, 'older'), name: 'Older', lastOpened: '2026-09-20T08:00:00.000Z' }
    ]
  })

  afterEach(() => {
    rmSync(dir, { recursive: true, force: true })
  })

  it('reopens the most recent knowledge base when it is still valid', () => {
    expect(decideStartup({ explicit: null, reopenEnabled: true, recent, pathKind })).toEqual({
      kind: 'open',
      root: kb,
      reopened: true
    })
  })

  it('shows the start page with the reason when the folder is gone', () => {
    rmSync(kb, { recursive: true })
    expect(decideStartup({ explicit: null, reopenEnabled: true, recent, pathKind })).toEqual({
      kind: 'start',
      notice: `The last knowledge base, My notes, was not found at ${kb}.`
    })
  })

  it('treats a file where the folder was as not found', () => {
    rmSync(kb, { recursive: true })
    writeFileSync(kb, 'not a folder', 'utf-8')
    const decision = decideStartup({ explicit: null, reopenEnabled: true, recent, pathKind })
    expect(decision).toEqual({
      kind: 'start',
      notice: `The last knowledge base, My notes, was not found at ${kb}.`
    })
  })

  it('shows the start page with the reason when the folder is no longer a knowledge base', () => {
    rmSync(join(kb, WORKSPACE_MARKER))
    expect(decideStartup({ explicit: null, reopenEnabled: true, recent, pathKind })).toEqual({
      kind: 'start',
      notice: `The last knowledge base, My notes, at ${kb} is no longer a knowledge base.`
    })
  })

  it('shows the plain start page when the setting is off', () => {
    expect(decideStartup({ explicit: null, reopenEnabled: false, recent, pathKind })).toEqual({
      kind: 'start',
      notice: null
    })
  })

  it('shows the plain start page when nothing was opened before', () => {
    expect(decideStartup({ explicit: null, reopenEnabled: true, recent: [], pathKind })).toEqual({
      kind: 'start',
      notice: null
    })
  })

  it('opens an explicitly requested folder regardless of the setting or the recent list', () => {
    const other = join(dir, 'other')
    for (const reopenEnabled of [true, false]) {
      expect(decideStartup({ explicit: other, reopenEnabled, recent, pathKind })).toEqual({
        kind: 'open',
        root: other,
        reopened: false
      })
    }
  })
})
