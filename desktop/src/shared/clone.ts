// The Clone Knowledge Base window's contract with the main process, and the
// pure checks it runs while the person types. The core (`kos clone`) checks
// the URL and the folder again; these only give feedback before it runs.

/** IPC channels of the clone window. The main process answers them only for that window. */
export const CLONE_IPC = {
  defaults: 'clone:defaults',
  chooseParent: 'clone:choose-parent',
  start: 'clone:start',
  cancel: 'clone:cancel',
  progress: 'clone:progress',
  open: 'clone:open',
  close: 'clone:close'
} as const

export interface CloneDefaults {
  /** The folder new clones go into unless the person picks another. */
  parent: string
}

export interface CloneRequest {
  url: string
  parent: string
  name: string
}

/** One progress report from `kos clone --json`. */
export interface CloneProgress {
  phase: 'clone' | 'check' | 'index'
  line: string | null
  percent: number | null
}

export type CloneResult =
  | {
      ok: true
      root: string
      name: string | null
      /** `kos lint` findings; with any, the knowledge base is not opened by itself. */
      issues: Array<{ path: string; message: string }>
      indexError: string | null
    }
  | { ok: false; error: string; detail: string }

/** The only API the clone window's preload script exposes. */
export interface CloneApi {
  defaults: () => Promise<CloneDefaults>
  chooseParent: (current: string) => Promise<string | null>
  start: (request: CloneRequest) => Promise<CloneResult>
  cancel: () => Promise<void>
  onProgress: (callback: (progress: CloneProgress) => void) => () => void
  open: (root: string) => Promise<void>
  close: () => Promise<void>
}

const SCHEMES = new Set(['https', 'http', 'ssh', 'git', 'file'])
const WINDOWS_RESERVED = /^(con|prn|aux|nul|com\d|lpt\d)$/i

/** Why a Git URL cannot be used, as a key of `CLONE_TEXT.urlErrors`, or null when it looks fine. */
export function gitUrlProblem(
  raw: string
): 'empty' | 'spaces' | 'scheme' | 'password' | 'shape' | null {
  const url = raw.trim()
  if (url === '') return 'empty'
  if (/\s/.test(url) || url.startsWith('-')) return 'spaces'
  const scheme = /^([A-Za-z][A-Za-z0-9+.-]*):\/\//.exec(url)
  if (scheme) {
    if (!SCHEMES.has(scheme[1].toLowerCase())) return 'scheme'
    // `new URL` would read the path of `https:///x` as its host.
    if (scheme[1].toLowerCase() !== 'file' && url.charAt(scheme[0].length) === '/') return 'shape'
    let parsed: URL
    try {
      parsed = new URL(url)
    } catch {
      return 'shape'
    }
    if (parsed.password !== '') return 'password'
    if (scheme[1].toLowerCase() !== 'file' && parsed.hostname === '') return 'shape'
    return null
  }
  if (/^[A-Za-z]:[\\/]/.test(url) || url.startsWith('\\\\') || url.startsWith('/')) return null
  if (/^(?:[^@/\\:]+@)?[^@/\\:]{2,}:[^\\].*$/.test(url)) return null
  return 'shape'
}

/**
 * The folder name a clone of `raw` gets by default: the repository's last
 * path segment without `.git`, made safe as a Windows folder name. Empty
 * when nothing usable is left, so the person types one.
 */
export function folderNameFromUrl(raw: string): string {
  let url = raw.trim().replace(/[\\/]+$/, '')
  url = url.replace(/[?#].*$/, '')
  const last = url.split(/[\\/:]/).pop() ?? ''
  let name = last.replace(/\.git$/i, '')
  try {
    name = decodeURIComponent(name)
  } catch {
    // Keep it as typed.
  }
  name = name
    // eslint-disable-next-line no-control-regex
    .replace(/[<>:"/\\|?*\u0000-\u001f]/g, '-')
    .replace(/^[\s.]+|[\s.]+$/g, '')
  if (name === '' || WINDOWS_RESERVED.test(name)) return ''
  return name.slice(0, 80)
}

/** Why a folder name cannot be used, as a key of `CLONE_TEXT.nameErrors`, or null. */
export function folderNameProblem(raw: string): 'empty' | 'characters' | 'reserved' | null {
  const name = raw.trim()
  if (name === '') return 'empty'
  // eslint-disable-next-line no-control-regex
  if (/[<>:"/\\|?*\u0000-\u001f]/.test(name) || name === '.' || name === '..' || /[. ]$/.test(name))
    return 'characters'
  if (WINDOWS_RESERVED.test(name)) return 'reserved'
  return null
}
