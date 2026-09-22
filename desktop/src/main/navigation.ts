// Decides where the window may navigate: only to the running core's own
// origin or back to the start page. Everything else is blocked; http(s)
// links are handed to the system browser instead.

export type NavigationDecision = 'allow' | 'open-external' | 'block'

function origin(url: string): string | null {
  try {
    const parsed = new URL(url)
    if (parsed.protocol === 'file:') return `file://${parsed.pathname}`
    // Opaque origins (javascript:, data:, custom schemes) never match anything.
    return parsed.origin === 'null' ? null : parsed.origin
  } catch {
    return null
  }
}

export function decideNavigation(
  target: string,
  allowedOrigins: ReadonlyArray<string | null>
): NavigationDecision {
  const targetOrigin = origin(target)
  if (targetOrigin === null) return 'block'
  if (allowedOrigins.some((allowed) => allowed !== null && origin(allowed) === targetOrigin)) {
    return 'allow'
  }
  return targetOrigin.startsWith('http:') || targetOrigin.startsWith('https:')
    ? 'open-external'
    : 'block'
}
