import { describe, expect, it } from 'vitest'
import {
  addNotice,
  answerWithin,
  LeaveGuard,
  leavesAnyway,
  NO_ANSWER,
  noAnswerDialog,
  removeNotice,
  UNSAVED_ACTION,
  unsavedChangesDialog,
  UPDATE_ACTION,
  updateNotice
} from './chromeState'

describe('notices', () => {
  it('replace one with the same key and keep the newest last', () => {
    const a = updateNotice({ kind: 'message', message: 'Checking' })
    const b = { key: 'referat', tone: 'info' as const, message: 'Referat', actions: [] }
    const c = updateNotice({ kind: 'ready', version: '0.7.0' })
    const notices = addNotice(addNotice(addNotice([], a), b), c)
    expect(notices.map((notice) => notice.key)).toEqual(['referat', 'update'])
    expect(notices[1]).toBe(c)
    expect(removeNotice(notices, 'referat')).toEqual([c])
  })

  it('offer Restart to update for a ready update and nothing to act on for messages', () => {
    const ready = updateNotice({ kind: 'ready', version: '0.7.0' })
    expect(ready.message).toBe('Knowledge OS 0.7.0 is ready to install.')
    expect(ready.actions.map((action) => [action.id, action.label])).toEqual([
      [UPDATE_ACTION.restart, 'Restart to update'],
      [UPDATE_ACTION.later, 'Later']
    ])
    const message = updateNotice({ kind: 'message', message: 'Up to date.', detail: 'v1' })
    expect(message).toMatchObject({ message: 'Up to date.', detail: 'v1', actions: [] })
  })
})

describe('the unsaved-changes dialog', () => {
  it('keeps editing by default', () => {
    const dialog = unsavedChangesDialog(3)
    expect(dialog.id).toBe(3)
    expect(dialog.cancelId).toBe(UNSAVED_ACTION.keep)
    expect(dialog.actions.map((action) => action.label)).toEqual([
      'Keep editing',
      'Discard changes'
    ])
  })
})

describe('a page that does not answer', () => {
  it('gives NO_ANSWER after the timeout, and the answer when it comes first', async () => {
    const never = new Promise<boolean>(() => undefined)
    await expect(answerWithin(never, 10)).resolves.toBe(NO_ANSWER)
    await expect(answerWithin(Promise.resolve(false), 1000)).resolves.toBe(false)
    await expect(answerWithin(Promise.resolve(true), 1000)).resolves.toBe(true)
  })

  it('is asked about with staying as the default', () => {
    const dialog = noAnswerDialog()
    expect(dialog.buttons).toEqual(['Cancel', 'Leave anyway'])
    expect(leavesAnyway(dialog.defaultId)).toBe(false)
    expect(leavesAnyway(dialog.cancelId)).toBe(false)
    expect(leavesAnyway(dialog.buttons.indexOf('Leave anyway'))).toBe(true)
  })
})

function guard(
  dirty: boolean,
  answer: string = UNSAVED_ACTION.keep
): { leave: LeaveGuard; asked: number[] } {
  const asked: number[] = []
  const leave = new LeaveGuard({
    hasUnsavedChanges: async () => dirty,
    ask: async () => {
      asked.push(1)
      return answer
    },
    askNoAnswer: async () => false
  })
  return { leave, asked }
}

describe('LeaveGuard', () => {
  it('leaves a clean page without asking', async () => {
    const { leave, asked } = guard(false)
    let ran = false
    await leave.leave(() => (ran = true))
    expect(ran).toBe(true)
    expect(asked).toEqual([])
  })

  it('keeps the page when the person keeps editing', async () => {
    const { leave, asked } = guard(true, UNSAVED_ACTION.keep)
    let ran = false
    let kept = false
    await leave.leave(
      () => (ran = true),
      () => (kept = true)
    )
    expect([ran, kept, asked.length]).toEqual([false, true, 1])
    // The page objects on its own later: no old attempt comes back.
    expect(leave.unloadPrevented()).toEqual({ allow: false, retry: null })
  })

  it('lets exactly one unload through after a discard', async () => {
    const { leave } = guard(true, UNSAVED_ACTION.discard)
    let ran = false
    await leave.leave(() => (ran = true))
    expect(ran).toBe(true)
    expect(leave.unloadPrevented().allow).toBe(true)
    expect(leave.unloadPrevented().allow).toBe(false)
  })

  it('asks once when two leaves race, and both follow the answer', async () => {
    const { leave, asked } = guard(true, UNSAVED_ACTION.discard)
    const results = await Promise.all([leave.confirm(), leave.confirm()])
    expect(results).toEqual([true, true])
    expect(asked.length).toBe(1)
  })

  it('offers the attempt again when the page objects without a confirmation', async () => {
    const { leave } = guard(false)
    let runs = 0
    await leave.leave(() => runs++)
    // The page became dirty between the check and the unload.
    const { allow, retry } = leave.unloadPrevented()
    expect(allow).toBe(false)
    expect(retry).not.toBeNull()
    const again = new LeaveGuard({
      hasUnsavedChanges: async () => false,
      ask: async () => UNSAVED_ACTION.discard,
      askNoAnswer: async () => false
    })
    await again.leave(retry!, undefined, true)
    expect(runs).toBe(2)
    expect(again.unloadPrevented().allow).toBe(true)
  })

  it('treats a page that cannot answer as clean', async () => {
    const leave = new LeaveGuard({
      hasUnsavedChanges: async () => {
        throw new Error('gone')
      },
      ask: async () => UNSAVED_ACTION.keep,
      askNoAnswer: async () => false
    })
    expect(await leave.confirm()).toBe(true)
  })

  it('asks instead of assuming a page that does not answer is clean', async () => {
    for (const leaveAnyway of [false, true]) {
      const asked: string[] = []
      const leave = new LeaveGuard({
        hasUnsavedChanges: async () => NO_ANSWER,
        ask: async () => {
          asked.push('unsaved')
          return UNSAVED_ACTION.discard
        },
        askNoAnswer: async () => {
          asked.push('no-answer')
          return leaveAnyway
        }
      })
      let ran = false
      await leave.leave(() => (ran = true))
      expect([ran, asked]).toEqual([leaveAnyway, ['no-answer']])
      // Leaving anyway also lets the page's own objection through, once.
      expect(leave.unloadPrevented().allow).toBe(leaveAnyway)
    }
  })

  it('forgets an approval once the page is left', async () => {
    const { leave } = guard(true, UNSAVED_ACTION.discard)
    await leave.confirm()
    leave.reset()
    expect(leave.unloadPrevented().allow).toBe(false)
  })
})
