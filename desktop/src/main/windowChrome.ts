// The shell's own window frame. Every window hides the native title bar and
// keeps Windows' own minimise, maximise, and close buttons through the
// title-bar overlay, coloured from the design tokens; src/chrome/windowChrome.ts
// draws the rest of the title bar into the page. For the main window this
// module also owns the chrome's state (menu, notices, dialog), answers its
// IPC, and runs the menu's keyboard shortcuts. For the small windows that
// show one page of the app's own (clone, Referat import) it builds the
// window and answers its IPC for that window only.

import {
  BrowserWindow,
  ipcMain,
  nativeTheme,
  type BrowserWindowConstructorOptions,
  type IpcMainEvent,
  type IpcMainInvokeEvent
} from 'electron'
import {
  CHROME_IPC,
  TITLE_BAR_COLORS,
  TITLE_BAR_HEIGHT,
  type ChromeDialog,
  type ChromeState,
  type ChromeTheme,
  type MenuView,
  type Notice
} from '../shared/chrome'
import { SHELL_TEXT } from '../shared/shellText'
import appIcon from '../../build/icon.ico?asset'
import { addNotice, removeNotice } from './chromeState'
import { matchAccelerator, type MenuSpec } from './menuModel'

export function systemTheme(): ChromeTheme {
  return nativeTheme.shouldUseDarkColors ? 'dark' : 'light'
}

function overlay(theme: ChromeTheme): Electron.TitleBarOverlayOptions {
  return { ...TITLE_BAR_COLORS[theme], height: TITLE_BAR_HEIGHT }
}

/** Options for a window with the shell's frame, coloured for `theme`. */
export function framedWindowOptions(
  theme: ChromeTheme = systemTheme()
): Pick<BrowserWindowConstructorOptions, 'titleBarStyle' | 'titleBarOverlay'> {
  return { titleBarStyle: 'hidden', titleBarOverlay: overlay(theme) }
}

function colourControls(window: BrowserWindow, theme: ChromeTheme): void {
  // macOS draws its own traffic lights and has no overlay to colour.
  if (process.platform === 'darwin' || window.isDestroyed()) return
  window.setTitleBarOverlay(overlay(theme))
}

/** A window without a menu follows the system theme, as its page does. */
export function followSystemTheme(window: BrowserWindow): void {
  const update = (): void => colourControls(window, systemTheme())
  nativeTheme.on('updated', update)
  window.on('closed', () => nativeTheme.off('updated', update))
}

export interface PageWindowOptions {
  parent?: BrowserWindow
  modal?: boolean
  width: number
  height: number
  minWidth: number
  minHeight: number
  title: string
  /** The one page the window shows. */
  pageUrl: string
  /** Absolute path of the page's own preload script. */
  preloadPath: string
}

/**
 * A framed, sandboxed window without a menu that shows only `pageUrl` (a
 * reload is allowed): no other navigation, no new windows.
 */
export function createPageWindow(options: PageWindowOptions): BrowserWindow {
  const { pageUrl, preloadPath, ...size } = options
  const window = new BrowserWindow({
    ...size,
    show: false,
    icon: appIcon,
    backgroundColor: nativeTheme.shouldUseDarkColors ? '#15181b' : '#fbfaf7',
    ...framedWindowOptions(),
    autoHideMenuBar: true,
    webPreferences: {
      preload: preloadPath,
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true
    }
  })
  window.setMenu(null)
  followSystemTheme(window)
  window.on('ready-to-show', () => window.show())
  const ownPage = (url: string): boolean => url.split(/[?#]/)[0] === pageUrl
  const guard = (navigation: Electron.Event, url: string): void => {
    if (!ownPage(url)) navigation.preventDefault()
  }
  window.webContents.on('will-navigate', guard)
  window.webContents.on('will-redirect', guard)
  window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }))
  void window.loadURL(pageUrl)
  return window
}

export type PageHandler = <A extends unknown[], R>(
  channel: string,
  action: (event: IpcMainInvokeEvent, ...args: A) => Promise<R>
) => void

/**
 * Registers IPC handlers that answer only calls from `window()`'s own page;
 * any other caller, the reader UI included, gets an error.
 */
export function handleFrom(window: () => BrowserWindow | null): PageHandler {
  return <A extends unknown[], R>(
    channel: string,
    action: (event: IpcMainInvokeEvent, ...args: A) => Promise<R>
  ): void => {
    ipcMain.handle(channel, (event, ...args) => {
      const own = window()
      if (own === null || own.isDestroyed() || event.sender !== own.webContents) {
        throw new Error('not allowed from this page')
      }
      return action(event, ...(args as A))
    })
  }
}

export interface MainChromeHost {
  /** Whether a page at `url` may use the chrome: the start page or the open knowledge base. */
  allowedPage: (url: string) => boolean
  /** Runs a menu command. */
  command: (command: string) => void
}

/**
 * The main window's chrome. The state outlives page loads (the start page
 * and the reader replace each other in the window), so a notice or dialog
 * stays up when the page under it changes.
 */
export class MainWindowChrome {
  private window: BrowserWindow | null = null
  private menus: MenuSpec[] = []
  private state: ChromeState = {
    menus: [],
    workspace: null,
    notices: [],
    dialog: null,
    titleAction: null,
    labels: { menubar: SHELL_TEXT.titleBar.menubar, dismiss: SHELL_TEXT.titleBar.dismiss },
    zoomFactor: 1,
    fullScreen: false
  }
  private noticeHandlers = new Map<string, (action: string) => void>()
  private dialogQueue: Array<{ dialog: ChromeDialog; resolve: (action: string) => void }> = []
  private nextDialogId = 1

  constructor(private readonly host: MainChromeHost) {
    const fromPage = (event: IpcMainEvent | IpcMainInvokeEvent): boolean => {
      const window = this.window
      return (
        window !== null &&
        !window.isDestroyed() &&
        event.sender === window.webContents &&
        event.senderFrame !== null &&
        event.senderFrame === event.sender.mainFrame &&
        this.host.allowedPage(event.senderFrame.url)
      )
    }
    ipcMain.handle(CHROME_IPC.getState, (event) => {
      if (!fromPage(event)) throw new Error('not allowed from this page')
      this.refreshZoom()
      return this.state
    })
    ipcMain.on(CHROME_IPC.command, (event, command: unknown) => {
      if (fromPage(event) && typeof command === 'string' && this.state.dialog === null) {
        this.host.command(command)
      }
    })
    ipcMain.on(CHROME_IPC.notice, (event, key: unknown, action: unknown) => {
      if (fromPage(event) && typeof key === 'string' && typeof action === 'string') {
        this.answerNotice(key, action)
      }
    })
    ipcMain.on(CHROME_IPC.dialog, (event, id: unknown, action: unknown) => {
      if (fromPage(event) && typeof id === 'number' && typeof action === 'string') {
        this.answerDialog(id, action)
      }
    })
    ipcMain.on(CHROME_IPC.theme, (event, theme: unknown) => {
      const window = this.window
      if (window !== null && fromPage(event) && (theme === 'light' || theme === 'dark')) {
        colourControls(window, theme)
      }
    })
  }

  /** Takes over `window`: its shortcuts, and its page's chrome. */
  attach(window: BrowserWindow): void {
    this.window = window
    this.update({ fullScreen: window.isFullScreen() })
    window.on('enter-full-screen', () => this.update({ fullScreen: true }))
    window.on('leave-full-screen', () => this.update({ fullScreen: false }))
    window.webContents.on('before-input-event', (event, input) => {
      // macOS runs the shortcuts through its native application menu.
      if (process.platform === 'darwin' || this.state.dialog !== null) return
      const command = matchAccelerator(input, this.menus)
      if (command === null) return
      event.preventDefault()
      this.host.command(command)
    })
    window.webContents.on('zoom-changed', () => this.refreshZoom())
    window.on('closed', () => {
      if (this.window === window) this.window = null
      // Nobody is left to answer: every open question takes its safe answer.
      for (const { dialog, resolve } of this.dialogQueue.splice(0)) resolve(dialog.cancelId)
      this.state = { ...this.state, dialog: null }
    })
  }

  setMenus(menus: MenuSpec[], views: MenuView[]): void {
    this.menus = menus
    this.update({ menus: views })
  }

  setWorkspace(name: string | null): void {
    if (name !== this.state.workspace) this.update({ workspace: name })
  }

  setTitleAction(action: ChromeState['titleAction']): void {
    if (JSON.stringify(action) !== JSON.stringify(this.state.titleAction)) {
      this.update({ titleAction: action })
    }
  }

  /** Shows `notice`, replacing one with the same key; `onAction` hears which button was chosen. */
  showNotice(notice: Notice, onAction?: (action: string) => void): void {
    if (onAction) this.noticeHandlers.set(notice.key, onAction)
    else this.noticeHandlers.delete(notice.key)
    this.update({ notices: addNotice(this.state.notices, notice) })
  }

  /** Shows `dialog` (after any already open) and resolves with the chosen action. */
  ask(make: (id: number) => ChromeDialog): Promise<string> {
    const dialog = make(this.nextDialogId++)
    if (this.window === null || this.window.isDestroyed()) return Promise.resolve(dialog.cancelId)
    return new Promise((resolve) => {
      this.dialogQueue.push({ dialog, resolve })
      if (this.state.dialog === null) this.update({ dialog })
    })
  }

  /** Call after changing the page's zoom. */
  refreshZoom(): void {
    const window = this.window
    if (window === null || window.isDestroyed()) return
    const zoomFactor = window.webContents.getZoomFactor()
    if (zoomFactor !== this.state.zoomFactor) this.update({ zoomFactor })
  }

  private answerNotice(key: string, action: string): void {
    const handler = this.noticeHandlers.get(key)
    this.noticeHandlers.delete(key)
    this.update({ notices: removeNotice(this.state.notices, key) })
    handler?.(action)
  }

  private answerDialog(id: number, action: string): void {
    const current = this.dialogQueue[0]
    if (current === undefined || current.dialog.id !== id) return
    if (!current.dialog.actions.some((item) => item.id === action)) return
    this.dialogQueue.shift()
    this.update({ dialog: this.dialogQueue[0]?.dialog ?? null })
    current.resolve(action)
  }

  private update(change: Partial<ChromeState>): void {
    this.state = { ...this.state, ...change }
    const window = this.window
    if (window !== null && !window.isDestroyed()) {
      window.webContents.send(CHROME_IPC.state, this.state)
    }
  }
}
