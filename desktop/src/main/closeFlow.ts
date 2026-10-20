// Closing the main window, quitting, and restarting into a downloaded update
// as pure state transitions, kept apart from Electron so they are
// unit-testable. index.ts feeds in what happened and carries out the action.
//
// Every close (the close button, Alt+F4, File → Exit, quitting, Restart to
// update) first deals with unsaved edits in the reader (the LeaveGuard in
// chromeState.ts asks); keeping them keeps the window and cancels a pending
// restart or quit. Then the reader writes the decision actions still waiting
// for Undo, and only then does the window close for real (which stops the
// core, and afterwards starts a pending update's installer).

export interface CloseState {
  /**
   * The main window's close: `open` when none is under way, `asking` while
   * a close waits on the unsaved-changes question and the reader's flush,
   * `confirmed` once it passed both and the next close goes through.
   */
  window: 'open' | 'asking' | 'confirmed'
  /** Set by "Restart to update" until the window closes or the person keeps editing. */
  restartPending: boolean
  /** Set once quitting starts, so a close held back to flush the reader resumes the quit. */
  quitRequested: boolean
}

export type CloseEvent =
  /** A new main window; its close starts over. */
  | { type: 'window-created' }
  /** The window's `close` event. */
  | { type: 'close-requested' }
  /** The person kept their edits when the window's close asked. */
  | { type: 'close-kept' }
  /**
   * The close passed the unsaved-changes question and the reader's flush
   * finished. `windowGone` when the window was destroyed in the meantime.
   */
  | { type: 'flushed'; windowGone: boolean }
  /** The person kept their edits when anything else that leaves the page asked. */
  | { type: 'keep-editing' }
  /** The page objected to an unload that was not confirmed (`will-prevent-unload`). */
  | { type: 'unload-objected' }
  /** The app's `before-quit`. */
  | { type: 'quit-requested' }
  /** "Restart to update"; `hasWindow` when a main window is open to close first. */
  | { type: 'restart-requested'; hasWindow: boolean }
  /** The window's `closed` event. */
  | { type: 'window-closed' }

export type CloseAction =
  /** Nothing to do. For `close-requested`: hold the window open, a close is already under way. */
  | 'none'
  /** Let the `close` event through. */
  | 'let-close'
  /** Hold the window open and ask about unsaved edits (then flush the reader). */
  | 'ask'
  /** Quit the app (which closes the now confirmed window). */
  | 'quit'
  /** Close the window. */
  | 'close-window'
  /** Run the downloaded update's installer. */
  | 'install'
  /** No window to close: stop the core and run the installer right away. */
  | 'stop-core-and-install'

export interface CloseTransition {
  state: CloseState
  action: CloseAction
}

export const INITIAL_CLOSE_STATE: CloseState = {
  window: 'open',
  restartPending: false,
  quitRequested: false
}

/** Keeping the edits cancels a pending restart or quit, and a confirmed close. */
function keepEditing(state: CloseState): CloseState {
  return {
    window: state.window === 'confirmed' ? 'open' : state.window,
    restartPending: false,
    quitRequested: false
  }
}

export function nextCloseState(state: CloseState, event: CloseEvent): CloseTransition {
  const to = (next: CloseState, action: CloseAction = 'none'): CloseTransition => ({
    state: next,
    action
  })

  switch (event.type) {
    case 'window-created':
      return to({ ...state, window: 'open' })
    case 'close-requested':
      if (state.window === 'confirmed') return to(state, 'let-close')
      // A second request while the first is being asked or flushed waits for it.
      if (state.window === 'asking') return to(state)
      return to({ ...state, window: 'asking' }, 'ask')
    case 'close-kept':
      return to({ ...keepEditing(state), window: 'open' })
    case 'flushed':
      // A destroyed window has nothing left to close; the next one starts over.
      if (event.windowGone) return to(state)
      return to({ ...state, window: 'confirmed' }, state.quitRequested ? 'quit' : 'close-window')
    case 'keep-editing':
      return to(keepEditing(state))
    case 'unload-objected':
      return to({ ...state, window: state.window === 'confirmed' ? 'open' : state.window })
    case 'quit-requested':
      return to({ ...state, quitRequested: true })
    case 'restart-requested':
      if (!event.hasWindow) return to(state, 'stop-core-and-install')
      return to({ ...state, restartPending: true }, 'close-window')
    case 'window-closed':
      if (!state.restartPending) return to(state)
      return to({ ...state, restartPending: false }, 'install')
  }
}
