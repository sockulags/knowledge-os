import { describe, expect, it } from 'vitest'
import { LeaveGuard, NO_ANSWER, UNSAVED_ACTION } from './chromeState'
import {
  INITIAL_CLOSE_STATE,
  nextCloseState,
  type CloseAction,
  type CloseEvent,
  type CloseState
} from './closeFlow'

function run(
  events: CloseEvent[],
  start: CloseState = INITIAL_CLOSE_STATE
): { state: CloseState; actions: CloseAction[] } {
  let state = start
  const actions: CloseAction[] = []
  for (const event of events) {
    const result = nextCloseState(state, event)
    state = result.state
    actions.push(result.action)
  }
  return { state, actions }
}

const state = (
  window: CloseState['window'],
  restartPending = false,
  quitRequested = false
): CloseState => ({
  window,
  restartPending,
  quitRequested
})

describe('single transitions', () => {
  const cases: Array<[string, CloseState, CloseEvent, CloseState, CloseAction]> = [
    [
      'a new window starts over',
      state('confirmed', true, true),
      { type: 'window-created' },
      state('open', true, true),
      'none'
    ],
    ['a first close asks', state('open'), { type: 'close-requested' }, state('asking'), 'ask'],
    [
      'a close while asking waits',
      state('asking'),
      { type: 'close-requested' },
      state('asking'),
      'none'
    ],
    [
      'a confirmed close goes through',
      state('confirmed'),
      { type: 'close-requested' },
      state('confirmed'),
      'let-close'
    ],
    [
      'keeping edits at close cancels restart and quit',
      state('asking', true, true),
      { type: 'close-kept' },
      state('open'),
      'none'
    ],
    [
      'a flushed close closes the window',
      state('asking'),
      { type: 'flushed', windowGone: false },
      state('confirmed'),
      'close-window'
    ],
    [
      'a flushed close resumes a quit',
      state('asking', false, true),
      { type: 'flushed', windowGone: false },
      state('confirmed', false, true),
      'quit'
    ],
    [
      'a flushed close keeps a pending restart',
      state('asking', true),
      { type: 'flushed', windowGone: false },
      state('confirmed', true),
      'close-window'
    ],
    [
      'a destroyed window needs nothing more',
      state('asking', true, true),
      { type: 'flushed', windowGone: true },
      state('asking', true, true),
      'none'
    ],
    [
      'a retried close that is flushed closes',
      state('open'),
      { type: 'flushed', windowGone: false },
      state('confirmed'),
      'close-window'
    ],
    [
      'keeping edits elsewhere cancels a confirmed close',
      state('confirmed', true, true),
      { type: 'keep-editing' },
      state('open'),
      'none'
    ],
    [
      'keeping edits elsewhere leaves a close being asked',
      state('asking', true, true),
      { type: 'keep-editing' },
      state('asking'),
      'none'
    ],
    [
      'an objected unload cancels a confirmed close',
      state('confirmed', true, true),
      { type: 'unload-objected' },
      state('open', true, true),
      'none'
    ],
    [
      'an objected unload leaves a close being asked',
      state('asking'),
      { type: 'unload-objected' },
      state('asking'),
      'none'
    ],
    [
      'quitting is remembered',
      state('open'),
      { type: 'quit-requested' },
      state('open', false, true),
      'none'
    ],
    [
      'restart closes the window first',
      state('open'),
      { type: 'restart-requested', hasWindow: true },
      state('open', true),
      'close-window'
    ],
    [
      'restart without a window installs now',
      state('open'),
      { type: 'restart-requested', hasWindow: false },
      state('open'),
      'stop-core-and-install'
    ],
    [
      'a closed window installs a pending update once',
      state('confirmed', true),
      { type: 'window-closed' },
      state('confirmed'),
      'install'
    ],
    [
      'a closed window without a restart does nothing',
      state('confirmed'),
      { type: 'window-closed' },
      state('confirmed'),
      'none'
    ]
  ]
  it.each(cases)('%s', (_name, from, event, to, action) => {
    expect(nextCloseState(from, event)).toEqual({ state: to, action })
  })
})

describe('sequences', () => {
  it('close: ask, flush, close, then let the close through', () => {
    const { state: end, actions } = run([
      { type: 'close-requested' },
      { type: 'flushed', windowGone: false },
      { type: 'close-requested' },
      { type: 'window-closed' }
    ])
    expect(actions).toEqual(['ask', 'close-window', 'let-close', 'none'])
    expect(end.window).toBe('confirmed')
  })

  it('quit: the held-back close resumes the quit', () => {
    const { actions } = run([
      { type: 'quit-requested' },
      { type: 'close-requested' },
      { type: 'flushed', windowGone: false },
      { type: 'close-requested' }
    ])
    expect(actions).toEqual(['none', 'ask', 'quit', 'let-close'])
  })

  it('restart for update: closes the window and installs once it has closed', () => {
    const { state: end, actions } = run([
      { type: 'restart-requested', hasWindow: true },
      { type: 'close-requested' },
      { type: 'flushed', windowGone: false },
      { type: 'close-requested' },
      { type: 'window-closed' }
    ])
    expect(actions).toEqual(['close-window', 'ask', 'close-window', 'let-close', 'install'])
    expect(end.restartPending).toBe(false)
  })

  it('restart for update: keeping the edits cancels the install', () => {
    const { state: end, actions } = run([
      { type: 'restart-requested', hasWindow: true },
      { type: 'close-requested' },
      { type: 'close-kept' },
      { type: 'window-closed' }
    ])
    expect(actions).toEqual(['close-window', 'ask', 'none', 'none'])
    expect(end).toEqual(INITIAL_CLOSE_STATE)
  })

  it('repeated close requests while closing ask only once', () => {
    const { actions } = run([
      { type: 'close-requested' },
      { type: 'close-requested' },
      { type: 'quit-requested' },
      { type: 'close-requested' },
      { type: 'flushed', windowGone: false }
    ])
    expect(actions).toEqual(['ask', 'none', 'none', 'none', 'quit'])
  })

  it('a page that objects after the close was confirmed is asked again', () => {
    const { state: end, actions } = run([
      { type: 'close-requested' },
      { type: 'flushed', windowGone: false },
      { type: 'unload-objected' },
      { type: 'close-requested' }
    ])
    expect(actions).toEqual(['ask', 'close-window', 'none', 'ask'])
    expect(end.window).toBe('asking')
  })
})

/**
 * The window's close as index.ts wires it: the LeaveGuard asks about unsaved
 * edits, then the flow decides. Resolves with every action taken.
 */
async function closeWith(
  dirty: boolean | typeof NO_ANSWER,
  answer: { choice?: string; leaveAnyway?: boolean },
  start: CloseState = INITIAL_CLOSE_STATE
): Promise<{ state: CloseState; actions: CloseAction[] }> {
  let current = start
  const actions: CloseAction[] = []
  const step = (event: CloseEvent): CloseAction => {
    const result = nextCloseState(current, event)
    current = result.state
    actions.push(result.action)
    return result.action
  }
  const guard = new LeaveGuard({
    hasUnsavedChanges: async () => dirty,
    ask: async () => answer.choice ?? UNSAVED_ACTION.keep,
    askNoAnswer: async () => answer.leaveAnyway ?? false
  })
  if (step({ type: 'close-requested' }) === 'ask') {
    await guard.leave(
      () => step({ type: 'flushed', windowGone: false }),
      () => step({ type: 'close-kept' })
    )
  }
  return { state: current, actions }
}

describe('unsaved changes at close', () => {
  const quitting = state('open', true, true)
  const cases: Array<
    [
      string,
      boolean | typeof NO_ANSWER,
      { choice?: string; leaveAnyway?: boolean },
      CloseAction,
      CloseState
    ]
  > = [
    ['none: the quit goes on', false, {}, 'quit', state('confirmed', true, true)],
    [
      'discarded: the quit goes on',
      true,
      { choice: UNSAVED_ACTION.discard },
      'quit',
      state('confirmed', true, true)
    ],
    [
      'kept: quit and restart are cancelled',
      true,
      { choice: UNSAVED_ACTION.keep },
      'none',
      state('open')
    ],
    [
      'no answer, leave anyway: the quit goes on',
      NO_ANSWER,
      { leaveAnyway: true },
      'quit',
      state('confirmed', true, true)
    ],
    [
      'no answer, cancel: quit and restart are cancelled',
      NO_ANSWER,
      { leaveAnyway: false },
      'none',
      state('open')
    ]
  ]
  it.each(cases)('%s', async (_name, dirty, answer, last, end) => {
    const { state: after, actions } = await closeWith(dirty, answer, quitting)
    expect(actions).toEqual(['ask', last])
    expect(after).toEqual(end)
  })
})
