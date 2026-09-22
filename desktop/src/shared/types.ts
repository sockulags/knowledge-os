/** IPC channel names shared by the main process and the preload script. */
export const IPC = {
  getState: 'shell:get-state',
  stateChanged: 'shell:state-changed',
  openWorkspace: 'workspace:open',
  createWorkspace: 'workspace:create',
  openRecent: 'workspace:open-recent',
  showStart: 'workspace:show-start',
  retry: 'workspace:retry'
} as const

export interface RecentWorkspace {
  root: string
  name: string
  /** ISO timestamp of the last successful open. */
  lastOpened: string
}

export type ErrorKind = 'python-missing' | 'invalid-workspace' | 'early-exit' | 'create-failed'

/** What the start page shows; while a workspace is open the window shows the reader instead. */
export type ShellState =
  | { kind: 'start'; recent: RecentWorkspace[] }
  | { kind: 'starting'; root: string; recent: RecentWorkspace[] }
  | { kind: 'ready'; root: string; name: string; url: string; recent: RecentWorkspace[] }
  | {
      kind: 'error'
      error: ErrorKind
      root: string | null
      message: string
      detail: string
      recent: RecentWorkspace[]
    }

/** The only API the preload script exposes to the start page. */
export interface DesktopApi {
  getState: () => Promise<ShellState>
  onStateChanged: (callback: (state: ShellState) => void) => () => void
  /** Shows a folder picker and opens the chosen workspace. */
  openWorkspace: () => Promise<void>
  /** Shows a folder picker for an empty folder and creates a workspace there with `kos init`. */
  createWorkspace: () => Promise<void>
  openRecent: (root: string) => Promise<void>
  showStart: () => Promise<void>
  /** Retries the failed action shown on the error screen, re-checking Python first. */
  retry: () => Promise<void>
}
