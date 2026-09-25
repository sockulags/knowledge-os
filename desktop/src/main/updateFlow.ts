// The update flow as pure state transitions, kept apart from electron-updater
// so it is unit-testable: what state the updater is in, what (if anything) to
// tell the person, and when "Restart to update" may be offered.

import { SHELL_TEXT, fillText } from '../shared/shellText'

const TEXT = SHELL_TEXT.update

export type UpdateState =
  | { phase: 'idle' }
  | { phase: 'checking'; manual: boolean }
  | { phase: 'downloading'; version: string; manual: boolean }
  /** Downloaded and verified; installing it needs a restart. */
  | { phase: 'ready'; version: string }

export type UpdateEvent =
  | { type: 'check'; manual: boolean }
  | { type: 'available'; version: string }
  | { type: 'not-available' }
  | { type: 'downloaded'; version: string }
  | { type: 'failed' }

/**
 * What to show the person. `ready` offers "Restart to update"; the others are
 * plain messages. Automatic checks only ever produce `ready`: everything else
 * about them, failures included, is logged and never shown.
 */
export type UpdateNotice =
  { kind: 'ready'; version: string } | { kind: 'message'; message: string; detail?: string }

export interface Transition {
  state: UpdateState
  notice: UpdateNotice | null
  /** True when the caller should start a check with electron-updater now. */
  startCheck: boolean
}

export const INITIAL_UPDATE_STATE: UpdateState = { phase: 'idle' }

function message(text: string, detail?: string): UpdateNotice {
  return detail === undefined
    ? { kind: 'message', message: text }
    : { kind: 'message', message: text, detail }
}

export function nextUpdateState(
  state: UpdateState,
  event: UpdateEvent,
  currentVersion: string
): Transition {
  const stay = (notice: UpdateNotice | null = null): Transition => ({
    state,
    notice,
    startCheck: false
  })

  switch (event.type) {
    case 'check':
      if (state.phase === 'idle') {
        return {
          state: { phase: 'checking', manual: event.manual },
          notice: null,
          startCheck: true
        }
      }
      if (!event.manual) return stay()
      if (state.phase === 'ready') return stay({ kind: 'ready', version: state.version })
      if (state.phase === 'downloading') {
        // A manual check joins the running download, so its outcome is reported.
        return {
          state: { ...state, manual: true },
          notice: message(
            fillText(TEXT.downloading, { version: state.version }),
            TEXT.downloadingDetail
          ),
          startCheck: false
        }
      }
      return { state: { phase: 'checking', manual: true }, notice: null, startCheck: false }

    case 'available':
      if (state.phase !== 'checking') return stay()
      return {
        state: { phase: 'downloading', version: event.version, manual: state.manual },
        notice: state.manual
          ? message(
              fillText(TEXT.availableDownloading, { version: event.version }),
              TEXT.downloadingDetail
            )
          : null,
        startCheck: false
      }

    case 'not-available':
      if (state.phase !== 'checking') return stay()
      return {
        state: { phase: 'idle' },
        notice: state.manual
          ? message(TEXT.upToDate, fillText(TEXT.upToDateDetail, { version: currentVersion }))
          : null,
        startCheck: false
      }

    case 'downloaded':
      // Always offered, also after an automatic check: restarting stays the person's choice.
      return {
        state: { phase: 'ready', version: event.version },
        notice: { kind: 'ready', version: event.version },
        startCheck: false
      }

    case 'failed':
      // A finished download stays usable even if a later check fails.
      if (state.phase === 'ready' || state.phase === 'idle') return stay()
      return {
        state: { phase: 'idle' },
        notice: state.manual
          ? message(
              state.phase === 'checking' ? TEXT.checkFailed : TEXT.downloadFailed,
              TEXT.failedDetail
            )
          : null,
        startCheck: false
      }
  }
}

/** "Restart to update" is offered only once an update has been downloaded. */
export function canRestartToUpdate(state: UpdateState): boolean {
  return state.phase === 'ready'
}

/**
 * The feed override for local update tests, baked in at build time. Only a
 * loopback http(s) URL is accepted, so even a build made with the variable set
 * by mistake can never fetch updates from anywhere but this machine.
 */
export function testFeedUrl(raw: string | undefined): string | null {
  if (raw === undefined || raw.trim() === '') return null
  let url: URL
  try {
    url = new URL(raw.trim())
  } catch {
    return null
  }
  const loopback = ['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname)
  return (url.protocol === 'http:' || url.protocol === 'https:') && loopback ? url.href : null
}
