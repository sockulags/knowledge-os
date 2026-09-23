import { describe, expect, it } from 'vitest'
import {
  INITIAL_UPDATE_STATE,
  canRestartToUpdate,
  nextUpdateState,
  testFeedUrl,
  type UpdateEvent,
  type UpdateNotice,
  type UpdateState
} from './updateFlow'

interface Run {
  state: UpdateState
  notices: UpdateNotice[]
  /** Indexes of the events that started a check with electron-updater. */
  checks: number[]
}

function run(events: UpdateEvent[], start: UpdateState = INITIAL_UPDATE_STATE): Run {
  let state = start
  const notices: UpdateNotice[] = []
  const checks: number[] = []
  for (const [index, event] of events.entries()) {
    const result = nextUpdateState(state, event, '0.2.0')
    state = result.state
    if (result.notice !== null) notices.push(result.notice)
    if (result.startCheck) checks.push(index)
  }
  return { state, notices, checks }
}

describe('automatic checks', () => {
  it('stay silent when there is no update', () => {
    const { state, notices, checks } = run([
      { type: 'check', manual: false },
      { type: 'not-available' }
    ])
    expect(state).toEqual({ phase: 'idle' })
    expect(notices).toEqual([])
    expect(checks).toEqual([0])
  })

  it('stay silent when offline', () => {
    const { state, notices } = run([{ type: 'check', manual: false }, { type: 'failed' }])
    expect(state).toEqual({ phase: 'idle' })
    expect(notices).toEqual([])
  })

  it('offer a restart only after the download finishes', () => {
    const found = run([
      { type: 'check', manual: false },
      { type: 'available', version: '0.3.0' }
    ])
    expect(found.notices).toEqual([])
    expect(canRestartToUpdate(found.state)).toBe(false)

    const done = run([{ type: 'downloaded', version: '0.3.0' }], found.state)
    expect(done.notices).toEqual([{ kind: 'ready', version: '0.3.0' }])
    expect(canRestartToUpdate(done.state)).toBe(true)
  })

  it('stay silent when the download fails', () => {
    const { state, notices } = run([
      { type: 'check', manual: false },
      { type: 'available', version: '0.3.0' },
      { type: 'failed' }
    ])
    expect(state).toEqual({ phase: 'idle' })
    expect(notices).toEqual([])
  })
})

describe('manual checks', () => {
  it('report being up to date with the current version', () => {
    const { notices } = run([{ type: 'check', manual: true }, { type: 'not-available' }])
    expect(notices).toEqual([
      { kind: 'message', message: 'Knowledge OS is up to date.', detail: 'You have version 0.2.0.' }
    ])
  })

  it('report a failed check in one short message', () => {
    const { state, notices } = run([{ type: 'check', manual: true }, { type: 'failed' }])
    expect(state).toEqual({ phase: 'idle' })
    expect(notices).toHaveLength(1)
    expect(notices[0]).toMatchObject({ kind: 'message', message: 'Could not check for updates.' })
  })

  it('report a found update as downloading, then offer the restart', () => {
    const { notices } = run([
      { type: 'check', manual: true },
      { type: 'available', version: '0.3.0' },
      { type: 'downloaded', version: '0.3.0' }
    ])
    expect(notices.map((notice) => notice.kind)).toEqual(['message', 'ready'])
  })

  it('join a running automatic check instead of starting another', () => {
    const { state, notices, checks } = run([
      { type: 'check', manual: false },
      { type: 'check', manual: true },
      { type: 'not-available' }
    ])
    expect(checks).toEqual([0])
    expect(state).toEqual({ phase: 'idle' })
    expect(notices).toHaveLength(1)
  })

  it('offer the restart again when an update is already downloaded', () => {
    const ready: UpdateState = { phase: 'ready', version: '0.3.0' }
    const { state, notices, checks } = run([{ type: 'check', manual: true }], ready)
    expect(state).toBe(ready)
    expect(notices).toEqual([{ kind: 'ready', version: '0.3.0' }])
    expect(checks).toEqual([])
  })
})

describe('a downloaded update', () => {
  it('stays ready through later automatic checks and failures', () => {
    const ready: UpdateState = { phase: 'ready', version: '0.3.0' }
    const { state, notices, checks } = run(
      [{ type: 'check', manual: false }, { type: 'failed' }],
      ready
    )
    expect(state).toBe(ready)
    expect(notices).toEqual([])
    expect(checks).toEqual([])
  })
})

describe('canRestartToUpdate', () => {
  it('is false before anything is downloaded', () => {
    expect(canRestartToUpdate({ phase: 'idle' })).toBe(false)
    expect(canRestartToUpdate({ phase: 'checking', manual: true })).toBe(false)
    expect(canRestartToUpdate({ phase: 'downloading', version: '0.3.0', manual: false })).toBe(
      false
    )
  })
})

describe('testFeedUrl', () => {
  it('is off when unset or empty', () => {
    expect(testFeedUrl(undefined)).toBeNull()
    expect(testFeedUrl('  ')).toBeNull()
  })

  it('accepts loopback http URLs', () => {
    expect(testFeedUrl('http://127.0.0.1:8765/')).toBe('http://127.0.0.1:8765/')
    expect(testFeedUrl('http://localhost:8765/feed')).toBe('http://localhost:8765/feed')
  })

  it('refuses any other host or scheme', () => {
    expect(testFeedUrl('https://example.com/')).toBeNull()
    expect(testFeedUrl('http://127.0.0.1.example.com/')).toBeNull()
    expect(testFeedUrl('file:///C:/feed')).toBeNull()
    expect(testFeedUrl('not a url')).toBeNull()
  })
})
