// What the main window's chrome shows besides its menu, as pure logic: the
// quiet notices under the title bar, the one dialog the window may be
// waiting on, and the unsaved-changes guard in front of everything that
// leaves the page (closing the window, restarting to update, reloading,
// opening another knowledge base). No Electron here, so it is unit-testable.

import type { ChromeAction, ChromeDialog, Notice } from '../shared/chrome'
import { SHELL_TEXT, fillText } from '../shared/shellText'
import type { UpdateNotice } from './updateFlow'

/** The notices after `notice` arrives: it replaces one with the same key, newest last. */
export function addNotice(notices: Notice[], notice: Notice): Notice[] {
  return [...notices.filter((item) => item.key !== notice.key), notice]
}

export function removeNotice(notices: Notice[], key: string): Notice[] {
  return notices.filter((item) => item.key !== key)
}

export const UPDATE_NOTICE_KEY = 'update'
export const UPDATE_ACTION = { restart: 'restart', later: 'later' } as const

/** The notice for an update event: "ready" offers the restart, the rest only inform. */
export function updateNotice(notice: UpdateNotice): Notice {
  if (notice.kind === 'ready') {
    return {
      key: UPDATE_NOTICE_KEY,
      tone: 'info',
      message: fillText(SHELL_TEXT.update.readyMessage, { version: notice.version }),
      detail: SHELL_TEXT.update.readyDetail,
      actions: [
        { id: UPDATE_ACTION.restart, label: SHELL_TEXT.update.restart, variant: 'primary' },
        { id: UPDATE_ACTION.later, label: SHELL_TEXT.update.later, variant: 'ghost' }
      ]
    }
  }
  const result: Notice = {
    key: UPDATE_NOTICE_KEY,
    tone: 'info',
    message: notice.message,
    actions: []
  }
  if (notice.detail !== undefined) result.detail = notice.detail
  return result
}

export const UNSAVED_ACTION = { discard: 'discard', keep: 'keep' } as const

/** The question before unsaved edits are discarded. Keeping them is the safe default. */
export function unsavedChangesDialog(id: number): ChromeDialog {
  const text = SHELL_TEXT.unsaved
  const actions: ChromeAction[] = [
    { id: UNSAVED_ACTION.keep, label: text.keep, variant: 'ghost' },
    { id: UNSAVED_ACTION.discard, label: text.discard, variant: 'danger' }
  ]
  return {
    id,
    tone: 'warning',
    title: text.title,
    message: text.message,
    detail: text.detail,
    actions,
    cancelId: UNSAVED_ACTION.keep
  }
}

/** What `hasUnsavedChanges` gives when the page did not answer in time. */
export const NO_ANSWER = 'no-answer'

/** `answer`, or `NO_ANSWER` when it has not settled within `timeoutMs`. */
export async function answerWithin<T>(
  answer: Promise<T>,
  timeoutMs: number
): Promise<T | typeof NO_ANSWER> {
  let timer: ReturnType<typeof setTimeout> | undefined
  const timeout = new Promise<typeof NO_ANSWER>((resolve) => {
    timer = setTimeout(() => resolve(NO_ANSWER), timeoutMs)
  })
  try {
    return await Promise.race([answer, timeout])
  } finally {
    clearTimeout(timer)
  }
}

/**
 * The question when the page does not say whether it holds unsaved edits.
 * It is a native message box, since the window's own dialogs are drawn by
 * the page that is not answering. Staying is the default.
 */
export function noAnswerDialog(): {
  type: 'warning'
  title: string
  message: string
  detail: string
  buttons: string[]
  defaultId: number
  cancelId: number
  noLink: true
} {
  const text = SHELL_TEXT.unsaved
  return {
    type: 'warning',
    title: text.title,
    message: text.noAnswerMessage,
    detail: text.noAnswerDetail,
    buttons: [text.cancel, text.leaveAnyway],
    defaultId: 0,
    cancelId: 0,
    noLink: true
  }
}

export interface AboutInfo {
  version: string
  electron: string
  chrome: string
  node: string
  logDir: string
}

/** Help → About Knowledge OS: the version, what it runs on, and where its log is. */
export function aboutDialog(info: AboutInfo): {
  type: 'info'
  title: string
  message: string
  detail: string
  buttons: string[]
  noLink: true
} {
  const text = SHELL_TEXT.about
  return {
    type: 'info',
    title: text.title,
    message: fillText(text.message, { version: info.version }),
    detail: fillText(text.detail, { ...info }),
    buttons: [text.ok],
    noLink: true
  }
}

/** Whether `noAnswerDialog`'s button `response` leaves the page. */
export function leavesAnyway(response: number): boolean {
  return response === 1
}

export interface LeaveGuardHooks {
  /**
   * Whether the page would object to being left (its `beforeunload` handler),
   * or `NO_ANSWER` when it did not say in time.
   */
  hasUnsavedChanges: () => Promise<boolean | typeof NO_ANSWER>
  /** Shows the unsaved-changes dialog and resolves with the chosen action. */
  ask: () => Promise<string>
  /** Asks whether to leave a page that did not answer; true leaves it. */
  askNoAnswer: () => Promise<boolean>
}

/**
 * Stands in front of every way of leaving the page. Electron only reports
 * that a page's `beforeunload` handler objected (`will-prevent-unload`) and
 * needs the answer synchronously, but the dialog is part of the page and so
 * answers later. So the guard asks first, before anything leaves:
 *
 * - `confirm()` checks the page; with unsaved edits it asks, and on
 *   "Discard changes" lets exactly one following unload through.
 * - `unloadPrevented()` answers Electron: through once after a confirmed
 *   discard, otherwise the page stays. When that happens without a
 *   confirmation (the page became dirty after the check), `retry` is asked
 *   again with the action that was attempted.
 */
export class LeaveGuard {
  private approved = false
  private asking: Promise<boolean> | null = null
  private attempt: (() => void) | null = null

  constructor(private readonly hooks: LeaveGuardHooks) {}

  /**
   * Resolves true when the page may be left, after asking if it has unsaved
   * edits. `objected` skips the check: the page has already objected.
   */
  confirm(objected = false): Promise<boolean> {
    // A second request while the question is open shares its answer.
    if (this.asking !== null) return this.asking
    const asking = this.check(objected).finally(() => {
      if (this.asking === asking) this.asking = null
    })
    this.asking = asking
    return asking
  }

  private async check(objected: boolean): Promise<boolean> {
    // Already confirmed, and the page has not been left yet: no second question.
    if (this.approved && !objected) return true
    let dirty: boolean | typeof NO_ANSWER = objected
    if (!dirty) {
      try {
        dirty = await this.hooks.hasUnsavedChanges()
      } catch {
        // A page that cannot answer (still loading, crashed) holds nothing to lose.
        dirty = false
      }
    }
    if (dirty === NO_ANSWER) {
      // A page that hangs may still hold edits: never assume it is clean.
      if (!(await this.hooks.askNoAnswer())) return false
      this.approved = true
      return true
    }
    if (!dirty) return true
    const choice = await this.hooks.ask()
    if (choice !== UNSAVED_ACTION.discard) return false
    this.approved = true
    return true
  }

  /**
   * Runs `action` once the page may be left; `cancelled` runs when the
   * person keeps editing. The action is remembered, so an unload the page
   * still objects to can ask again and retry it.
   */
  async leave(
    action: () => void,
    cancelled: () => void = () => undefined,
    objected = false
  ): Promise<void> {
    this.attempt = action
    if (await this.confirm(objected)) action()
    else {
      if (this.attempt === action) this.attempt = null
      cancelled()
    }
  }

  /**
   * Electron's `will-prevent-unload`. `allow` lets the unload through. When
   * the page objected without a confirmed discard, `retry` is the action to
   * ask about again (with `leave(retry, …, true)`), or null to keep the page.
   */
  unloadPrevented(): { allow: boolean; retry: (() => void) | null } {
    if (this.approved) {
      this.approved = false
      return { allow: true, retry: null }
    }
    // Offered once: a later objection does not bring back an old attempt.
    const retry = this.asking === null ? this.attempt : null
    this.attempt = null
    return { allow: false, retry }
  }

  /** The page was left or replaced: forget any approval and attempt. */
  reset(): void {
    this.approved = false
    this.attempt = null
  }
}
