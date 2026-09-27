/** IPC channel names shared by the main process and the preload script. */
export const IPC = {
  getState: 'shell:get-state',
  stateChanged: 'shell:state-changed',
  openWorkspace: 'workspace:open',
  createWorkspace: 'workspace:create',
  cloneWorkspace: 'workspace:clone',
  openRecent: 'workspace:open-recent',
  showStart: 'workspace:show-start',
  retry: 'workspace:retry',
  getSidebarWidth: 'reader:get-sidebar-width',
  setSidebarWidth: 'reader:set-sidebar-width',
  // The in-app agent (issue #90); only the reader UI may use these.
  agentList: 'agent:list',
  agentInstall: 'agent:install',
  agentStart: 'agent:start',
  agentPrompt: 'agent:prompt',
  agentCancel: 'agent:cancel',
  agentPermission: 'agent:permission',
  agentRestart: 'agent:restart',
  agentClose: 'agent:close',
  agentEvent: 'agent:event',
  /** A menu command for the reader UI: 'new-page' or 'toggle-agent'. */
  readerCommand: 'reader:command'
} as const

export interface RecentWorkspace {
  root: string
  name: string
  /** ISO timestamp of the last successful open. */
  lastOpened: string
}

export type ErrorKind =
  'python-missing' | 'core-missing' | 'invalid-workspace' | 'early-exit' | 'create-failed'

/** What the start page shows; while a workspace is open the window shows the reader instead. */
export type ShellState =
  | {
      kind: 'start'
      recent: RecentWorkspace[]
      /** Why the last knowledge base was not reopened on start, if it was not. */
      notice?: string
    }
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

/**
 * The only API the preload script exposes. Everything but the sidebar width
 * is for the start page; the main process rejects it from the reader UI.
 */
export interface DesktopApi {
  /**
   * The reader's remembered sidebar width, or null for its default. Read
   * synchronously so the reader lays out at that width from its first frame.
   * Only the reader UI gets an answer.
   */
  getSidebarWidth: () => number | null
  /** Remembers the reader's sidebar width; null forgets it. */
  setSidebarWidth: (width: number | null) => void
  getState: () => Promise<ShellState>
  onStateChanged: (callback: (state: ShellState) => void) => () => void
  /** Shows a folder picker and opens the chosen workspace. */
  openWorkspace: () => Promise<void>
  /** Shows a folder picker for an empty folder and creates a workspace there with `kos init`. */
  createWorkspace: () => Promise<void>
  /** Shows the Clone Knowledge Base window. */
  cloneWorkspace: () => Promise<void>
  openRecent: (root: string) => Promise<void>
  showStart: () => Promise<void>
  /** Retries the failed action shown on the error screen, re-checking Python first. */
  retry: () => Promise<void>
  /**
   * The in-app agent (issue #90). Only the reader UI gets answers; a call from
   * any other page is refused. Events are the shared ACP client's AgentEvent.
   */
  agent: {
    list: () => Promise<unknown[]>
    /** Install a provider's adapter on demand; progress arrives as `install` events. */
    installAdapter: (providerId: string) => Promise<void>
    start: (providerId: string) => Promise<{ state: string }>
    prompt: (text: string) => Promise<string>
    cancel: () => Promise<void>
    respondPermission: (requestId: string, optionId: string | null) => Promise<boolean>
    restart: () => Promise<void>
    close: () => Promise<void>
    onEvent: (callback: (event: unknown) => void) => () => void
  }
  /** Menu commands meant for the reader UI (New Page, Agent). */
  onReaderCommand: (callback: (command: string) => void) => () => void
}
