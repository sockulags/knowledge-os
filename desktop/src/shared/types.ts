/** IPC channel names shared by the main process and the preload script. */
export const IPC = {
  getState: 'shell:get-state',
  stateChanged: 'shell:state-changed',
  openWorkspace: 'workspace:open',
  createWorkspace: 'workspace:create',
  cloneWorkspace: 'workspace:clone',
  openRecent: 'workspace:open-recent',
  removeRecent: 'workspace:remove-recent',
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
  // Past conversations (issue #100), kept in the app's user-data folder.
  agentConversations: 'agent:conversations',
  agentConversationGet: 'agent:conversation-get',
  agentConversationSave: 'agent:conversation-save',
  agentConversationDelete: 'agent:conversation-delete',
  /** A menu command for the reader UI: 'new-page' or 'toggle-agent'. */
  readerCommand: 'reader:command'
} as const

export interface RecentWorkspace {
  root: string
  name: string
  /** ISO timestamp of the last successful open. */
  lastOpened: string
}

/** A recent entry on the start page; `missing` when its folder is gone (moved or deleted). */
export interface RecentEntry extends RecentWorkspace {
  missing: boolean
}

export type ErrorKind =
  'python-missing' | 'core-missing' | 'invalid-workspace' | 'early-exit' | 'create-failed'

/** What the start page shows; while a workspace is open the window shows the reader instead. */
export type ShellState =
  | {
      kind: 'start'
      recent: RecentEntry[]
      /** Why the last knowledge base was not reopened on start, if it was not. */
      notice?: string
    }
  | { kind: 'starting'; root: string; recent: RecentWorkspace[] }
  /** `kos init` is setting up a new knowledge base in `root`. */
  | { kind: 'creating'; root: string; recent: RecentWorkspace[] }
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
 * The only API the main window's preload script exposes. The workspace
 * actions (`getState` through `retry`) are for the start page, and the main
 * process rejects them from any other page. The sidebar width and `agent` are
 * for the reader UI of the open knowledge base, and the main process answers
 * them for no other page. `onStateChanged`, `onReaderCommand`, and
 * `agent.onEvent` only listen for events the main process sends.
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
  /** Removes a knowledge base from the recent list; its folder is left alone. */
  removeRecent: (root: string) => Promise<void>
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
    /** The open knowledge base's past conversations, newest first (issue #100). */
    conversations: () => Promise<unknown[]>
    conversation: (id: string) => Promise<unknown>
    saveConversation: (conversation: unknown) => Promise<unknown>
    deleteConversation: (id: string) => Promise<void>
  }
  /** Menu commands meant for the reader UI (New Page, Agent). */
  onReaderCommand: (callback: (command: string) => void) => () => void
}
