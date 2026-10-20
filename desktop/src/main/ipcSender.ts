// The one check every IPC handler runs on its caller: the message must come
// from the given window's own web contents, from its main frame (not an
// iframe), and from a page whose URL the handler accepts. Checking only the
// frame URL would let any frame or window that reaches an allowed origin
// through; checking only the sender would accept whatever page the window
// has navigated to.

/** The parts of an Electron window this check reads. */
export interface SenderWindow {
  isDestroyed: () => boolean
  webContents: unknown
}

/** The parts of an IPC event this check reads. */
export interface SenderEvent {
  sender: { mainFrame: unknown }
  senderFrame: { url: string } | null
}

export function isFrom(
  event: SenderEvent,
  window: SenderWindow | null,
  allowedUrl: (url: string) => boolean
): boolean {
  if (window === null || window.isDestroyed()) return false
  if (event.sender !== window.webContents) return false
  const frame = event.senderFrame
  if (frame === null || frame !== event.sender.mainFrame) return false
  return allowedUrl(frame.url)
}

/** Accepts exactly `pageUrl`, ignoring a query or fragment (a reload keeps it). */
export function isPage(pageUrl: string): (url: string) => boolean {
  return (url) => url.split(/[?#]/)[0] === pageUrl
}
