// File → Clone Knowledge Base…: a small window, with its own preload script,
// that asks for a Git URL and a folder, runs `kos clone` in the Python core
// (see cloneRunner.ts), shows its progress with a cancel button, and opens
// the result in the main window. The knowledge base open in the main window
// stays open until the clone has succeeded.

import { BrowserWindow, dialog, ipcMain, nativeTheme, type IpcMainInvokeEvent } from 'electron'
import { join } from 'path'
import appIcon from '../../build/icon.ico?asset'
import {
  CLONE_IPC,
  folderNameProblem,
  gitUrlProblem,
  type CloneDefaults,
  type CloneRequest,
  type CloneResult
} from '../shared/clone'
import { CLONE_TEXT } from '../shared/cloneText'
import { startClone, type CloneRun } from './cloneRunner'
import { followSystemTheme, framedWindowOptions } from './windowChrome'

export interface CloneHost {
  mainWindow: () => BrowserWindow | null
  /** URL of the clone window's page. */
  pageUrl: string
  /** Absolute path of the clone window's preload script. */
  preloadPath: string
  /** The folder new clones go into by default. */
  defaultParent: () => string
  /** The Python that runs the core, or null when none is usable (the main window then shows why). */
  python: () => Promise<string | null>
  pythonEnv: NodeJS.ProcessEnv
  /** Open a knowledge base in the main window. */
  open: (root: string) => Promise<void>
}

export interface CloneWindow {
  show: () => void
  /** Cancel a running clone, e.g. when the app quits. */
  cancelRunning: () => void
}

export function createCloneWindow(host: CloneHost): CloneWindow {
  let window: BrowserWindow | null = null
  let running: CloneRun | null = null

  function fromCloneWindow(event: IpcMainInvokeEvent): boolean {
    return window !== null && !window.isDestroyed() && event.sender === window.webContents
  }

  function handle<A extends unknown[], R>(
    channel: string,
    action: (event: IpcMainInvokeEvent, ...args: A) => Promise<R>
  ): void {
    ipcMain.handle(channel, (event, ...args) => {
      // Only the clone window may call these, never the reader UI.
      if (!fromCloneWindow(event)) throw new Error('not allowed from this page')
      return action(event, ...(args as A))
    })
  }

  handle(CLONE_IPC.defaults, async (): Promise<CloneDefaults> => ({ parent: host.defaultParent() }))

  handle(CLONE_IPC.chooseParent, async (_event, current: unknown): Promise<string | null> => {
    const options = {
      title: CLONE_TEXT.chooseParentTitle,
      buttonLabel: CLONE_TEXT.chooseParentButton,
      defaultPath: typeof current === 'string' && current !== '' ? current : host.defaultParent(),
      properties: ['openDirectory', 'createDirectory', 'promptToCreate'] as Array<
        'openDirectory' | 'createDirectory' | 'promptToCreate'
      >
    }
    const result =
      window !== null
        ? await dialog.showOpenDialog(window, options)
        : await dialog.showOpenDialog(options)
    return result.canceled || result.filePaths.length === 0 ? null : result.filePaths[0]
  })

  handle(CLONE_IPC.start, async (event, raw: unknown): Promise<CloneResult> => {
    const request = raw as Partial<CloneRequest> | null
    if (
      request === null ||
      typeof request !== 'object' ||
      typeof request.url !== 'string' ||
      typeof request.parent !== 'string' ||
      typeof request.name !== 'string'
    ) {
      return { ok: false, error: 'failed', detail: 'The clone request was not understood.' }
    }
    const urlProblem = gitUrlProblem(request.url)
    if (urlProblem !== null)
      return { ok: false, error: 'bad_url', detail: CLONE_TEXT.urlErrors[urlProblem] }
    const nameProblem = folderNameProblem(request.name)
    if (nameProblem !== null)
      return { ok: false, error: 'bad_name', detail: CLONE_TEXT.nameErrors[nameProblem] }
    if (request.parent.trim() === '')
      return { ok: false, error: 'bad_name', detail: CLONE_TEXT.parentEmpty }
    if (running !== null) return running.result
    const python = await host.python()
    if (python === null) {
      return { ok: false, error: 'core', detail: 'No usable Python core was found.' }
    }
    const sender = event.sender
    const run = startClone(
      python,
      request.url.trim(),
      join(request.parent.trim(), request.name.trim()),
      host.pythonEnv,
      (progress) => {
        if (!sender.isDestroyed()) sender.send(CLONE_IPC.progress, progress)
      }
    )
    running = run
    const result = await run.result
    if (running === run) running = null
    return result
  })

  handle(CLONE_IPC.cancel, async (): Promise<void> => {
    await running?.cancel()
  })

  handle(CLONE_IPC.open, async (_event, root: unknown): Promise<void> => {
    if (typeof root !== 'string' || root === '') return
    window?.close()
    await host.open(root)
  })

  handle(CLONE_IPC.close, async (): Promise<void> => {
    window?.close()
  })

  function show(): void {
    if (window !== null && !window.isDestroyed()) {
      window.focus()
      return
    }
    const parent = host.mainWindow() ?? undefined
    const created = new BrowserWindow({
      parent,
      modal: parent !== undefined,
      width: 640,
      height: 620,
      minWidth: 520,
      minHeight: 480,
      show: false,
      title: CLONE_TEXT.windowTitle,
      icon: appIcon,
      backgroundColor: nativeTheme.shouldUseDarkColors ? '#15181b' : '#fbfaf7',
      ...framedWindowOptions(),
      autoHideMenuBar: true,
      webPreferences: {
        preload: host.preloadPath,
        contextIsolation: true,
        nodeIntegration: false,
        sandbox: true
      }
    })
    window = created
    created.setMenu(null)
    followSystemTheme(created)
    created.on('ready-to-show', () => created.show())
    created.on('closed', () => {
      if (window === created) window = null
      // Closing the window mid-clone cancels it; the core removes what it wrote.
      void running?.cancel()
    })
    const ownPage = (url: string): boolean => url.split(/[?#]/)[0] === host.pageUrl
    const guard = (navigation: Electron.Event, url: string): void => {
      if (!ownPage(url)) navigation.preventDefault()
    }
    created.webContents.on('will-navigate', guard)
    created.webContents.on('will-redirect', guard)
    created.webContents.setWindowOpenHandler(() => ({ action: 'deny' }))
    void created.loadURL(host.pageUrl)
  }

  return {
    show,
    cancelRunning: () => {
      void running?.cancel()
    }
  }
}
