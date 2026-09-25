// The window chrome the shell draws itself: the title bar with the in-app
// menu, notices, and dialogs. The preload scripts draw it into every page
// the shell's windows show (see src/preload/chrome/), the main process owns
// its state (see src/main/windowChrome.ts). Only plain data crosses IPC.

/** Height of the title bar and of Windows' own window controls beside it. */
export const TITLE_BAR_HEIGHT = 36

/**
 * The title bar's colours, from the design tokens (`--color-bg-sidebar` and
 * `--color-text`): the window controls are drawn by Windows in these, so they
 * sit on the same ground as the rest of the bar.
 */
export const TITLE_BAR_COLORS = {
  light: { color: '#f2f0ea', symbolColor: '#1b1c1e' },
  dark: { color: '#101316', symbolColor: '#eae8e3' }
} as const

export type ChromeTheme = keyof typeof TITLE_BAR_COLORS

/** IPC between the main window's preload script and the main process. */
export const CHROME_IPC = {
  getState: 'chrome:get-state',
  state: 'chrome:state',
  command: 'chrome:command',
  notice: 'chrome:notice',
  dialog: 'chrome:dialog',
  theme: 'chrome:theme'
} as const

/** One entry of a menu, as the title bar draws it. */
export interface MenuItemView {
  /** The command the main process runs; empty for separators and submenus. */
  id: string
  type: 'normal' | 'checkbox' | 'separator' | 'submenu'
  label: string
  /** The shortcut as shown, such as "Ctrl+O". */
  accelerator?: string
  enabled: boolean
  checked?: boolean
  submenu?: MenuItemView[]
}

/** A top-level menu in the title bar. */
export interface MenuView {
  label: string
  items: MenuItemView[]
}

export interface ChromeAction {
  id: string
  label: string
  variant: 'primary' | 'secondary' | 'ghost' | 'danger'
}

/** A quiet message under the title bar. It never blocks the window. */
export interface Notice {
  /** A newer notice with the same key replaces the older one. */
  key: string
  tone: 'info' | 'warning'
  message: string
  detail?: string
  actions: ChromeAction[]
}

/** A question the window waits on, such as unsaved changes. */
export interface ChromeDialog {
  id: number
  tone: 'info' | 'warning'
  title: string
  message: string
  detail?: string
  actions: ChromeAction[]
  /** The action Escape and the scrim choose; it also gets the focus first. */
  cancelId: string
}

export interface ChromeState {
  menus: MenuView[]
  /** The open knowledge base's name, shown after the page title. */
  workspace: string | null
  notices: Notice[]
  dialog: ChromeDialog | null
  /** A command offered as a button in the title bar, such as "Restart to update". */
  titleAction: { command: string; label: string } | null
  /** Labels the title bar needs for screen readers. */
  labels: { menubar: string; dismiss: string }
  /** The page's zoom factor; the chrome keeps its own size whatever the page's zoom. */
  zoomFactor: number
  /** In full screen Windows shows no window controls, so the title bar needs no room for them. */
  fullScreen: boolean
}
