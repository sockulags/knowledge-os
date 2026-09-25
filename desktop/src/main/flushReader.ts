// Accepting or withdrawing a decision in the reader waits a few seconds for
// Undo before it is written (reader-ui/src/lib/pendingActions.ts). The core
// is stopped with a hard kill, so before the app stops it (switching
// knowledge base, closing the knowledge base, closing the window, quitting)
// it asks the reader to send what still waits and waits for the answer.
// Nothing waiting, or no reader page, costs one round trip.

/** The part of a BrowserWindow this needs, so it can be tested without Electron. */
export interface ReaderWindow {
  isDestroyed(): boolean
  webContents: { executeJavaScript(code: string, userGesture?: boolean): Promise<unknown> }
}

const FLUSH_SCRIPT =
  'typeof window.kosFlushPendingActions === "function" ? window.kosFlushPendingActions().then((n) => n, () => -1) : 0'

/**
 * Ask the reader in `window` to write every action still waiting for Undo,
 * and resolve once it has (or after `timeoutMs`, or at once when there is no
 * reader page). Never rejects. Resolves with how many were written, or null
 * when it could not tell.
 */
export async function flushReaderActions(
  window: ReaderWindow | null,
  timeoutMs = 8000
): Promise<number | null> {
  if (window === null || window.isDestroyed()) return null
  let timer: ReturnType<typeof setTimeout> | undefined
  const timeout = new Promise<null>((resolve) => {
    timer = setTimeout(() => resolve(null), timeoutMs)
  })
  try {
    const answer = await Promise.race([
      window.webContents.executeJavaScript(FLUSH_SCRIPT, true),
      timeout
    ])
    return typeof answer === 'number' ? answer : null
  } catch {
    return null
  } finally {
    clearTimeout(timer)
  }
}
