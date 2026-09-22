// Electron main process: one window that shows either the start page (pick,
// create, or reopen a workspace; errors) or the reader UI served by the Python
// core for the open workspace.

import { app, BrowserWindow, dialog, ipcMain, Menu, session, shell } from 'electron'
import type { IpcMainInvokeEvent, MenuItemConstructorOptions } from 'electron'
import { existsSync } from 'fs'
import { basename, join } from 'path'
import { pathToFileURL } from 'url'
import { IPC, type RecentWorkspace, type ShellState } from '../shared/types'
import { decideNavigation } from './navigation'
import {
  CoreProcess,
  initWorkspace,
  pythonEnvironment,
  resolvePython,
  type CoreFailure
} from './pythonCore'
import { findRepoRoot, interpreterCandidates } from './pythonInterpreter'
import { addRecent, loadRecent, saveRecent } from './recentWorkspaces'

// Development and test hook: keep this run's settings apart from others.
if (process.env['KOS_DESKTOP_USER_DATA']) {
  app.setPath('userData', process.env['KOS_DESKTOP_USER_DATA'])
}

const repoRoot = findRepoRoot(app.getAppPath(), existsSync)
const pythonEnv = pythonEnvironment(process.env, repoRoot)
const recentFile = join(app.getPath('userData'), 'recent-workspaces.json')

let mainWindow: BrowserWindow | null = null
let core: CoreProcess | null = null
let pythonExecutable: string | null = null
let recent: RecentWorkspace[] = loadRecent(recentFile)
let state: ShellState = { kind: 'start', recent }
/** Increments per open request so a slow, superseded start is discarded. */
let openGeneration = 0

const startPageUrl =
  !app.isPackaged && process.env['ELECTRON_RENDERER_URL']
    ? process.env['ELECTRON_RENDERER_URL']
    : pathToFileURL(join(__dirname, '../renderer/index.html')).href

function stopCoreSync(): void {
  core?.stopSync()
  core = null
}

function setState(next: ShellState): void {
  state = next
  const window = mainWindow
  if (window === null || window.isDestroyed()) return
  if (next.kind === 'ready') {
    window.setTitle(`${next.name || basename(next.root)} — Knowledge OS`)
    void window.loadURL(next.url)
  } else {
    window.setTitle('Knowledge OS')
    if (decideNavigation(window.webContents.getURL(), [startPageUrl]) === 'allow') {
      window.webContents.send(IPC.stateChanged, next)
    } else {
      void window.loadURL(startPageUrl)
    }
  }
  buildMenu()
}

function showError(root: string | null, failure: CoreFailure): void {
  setState({ kind: 'error', root, ...failure, recent })
}

async function ensurePython(): Promise<string | null> {
  if (pythonExecutable !== null) return pythonExecutable
  const candidates = interpreterCandidates({
    env: process.env,
    repoRoot,
    platform: process.platform,
    exists: existsSync
  })
  const result = await resolvePython(candidates, pythonEnv)
  if (!result.ok) {
    showError(null, result.failure)
    return null
  }
  pythonExecutable = result.executable
  return pythonExecutable
}

async function openWorkspace(root: string): Promise<void> {
  const generation = ++openGeneration
  const previous = core
  core = null
  setState({ kind: 'starting', root, recent })
  await previous?.stop()

  const executable = await ensurePython()
  if (executable === null || generation !== openGeneration) return
  const result = await CoreProcess.start(executable, root, pythonEnv)
  if (generation !== openGeneration) {
    if (result.ok) await result.core.stop()
    return
  }
  if (!result.ok) {
    showError(root, result.failure)
    return
  }

  core = result.core
  const started = result.core
  started.onUnexpectedExit((detail) => {
    if (core !== started) return
    core = null
    showError(root, {
      error: 'early-exit',
      message: 'The Python core stopped unexpectedly.',
      detail
    })
  })
  recent = addRecent(recent, {
    root,
    name: started.name || basename(root),
    lastOpened: new Date().toISOString()
  })
  try {
    saveRecent(recentFile, recent)
  } catch (error) {
    console.error('could not save the recent workspaces list', error)
  }
  setState({ kind: 'ready', root, name: started.name, url: started.url, recent })
}

async function showStart(): Promise<void> {
  openGeneration++
  const previous = core
  core = null
  await previous?.stop()
  setState({ kind: 'start', recent })
}

async function pickFolder(title: string, buttonLabel: string): Promise<string | null> {
  const options = {
    title,
    buttonLabel,
    properties: ['openDirectory', 'createDirectory', 'promptToCreate'] as Array<
      'openDirectory' | 'createDirectory' | 'promptToCreate'
    >
  }
  const result =
    mainWindow !== null
      ? await dialog.showOpenDialog(mainWindow, options)
      : await dialog.showOpenDialog(options)
  return result.canceled || result.filePaths.length === 0 ? null : result.filePaths[0]
}

async function chooseAndOpen(): Promise<void> {
  const folder = await pickFolder('Open knowledge base', 'Open')
  if (folder !== null) await openWorkspace(folder)
}

async function chooseAndCreate(): Promise<void> {
  const folder = await pickFolder(
    'Choose an empty folder for the new knowledge base',
    'Create knowledge base'
  )
  if (folder === null) return
  const executable = await ensurePython()
  if (executable === null) return
  const result = await initWorkspace(executable, folder, pythonEnv)
  if (!result.ok) {
    showError(null, result.failure)
    return
  }
  await openWorkspace(result.root)
}

function buildMenu(): void {
  const recentItems: MenuItemConstructorOptions[] =
    recent.length > 0
      ? recent.map((item) => ({
          label: `${item.name}  (${item.root})`,
          click: () => void openWorkspace(item.root)
        }))
      : [{ label: 'No recent knowledge bases', enabled: false }]
  const template: MenuItemConstructorOptions[] = [
    {
      label: 'File',
      submenu: [
        {
          label: 'Open Knowledge Base…',
          accelerator: 'CmdOrCtrl+O',
          click: () => void chooseAndOpen()
        },
        {
          label: 'New Knowledge Base…',
          accelerator: 'CmdOrCtrl+N',
          click: () => void chooseAndCreate()
        },
        { label: 'Open Recent', submenu: recentItems },
        { type: 'separator' },
        {
          label: 'Close Knowledge Base',
          enabled: state.kind === 'ready',
          click: () => void showStart()
        },
        { type: 'separator' },
        { role: 'quit' }
      ]
    },
    {
      label: 'View',
      submenu: [
        { role: 'reload' },
        { role: 'toggleDevTools' },
        { type: 'separator' },
        { role: 'resetZoom' },
        { role: 'zoomIn' },
        { role: 'zoomOut' },
        { type: 'separator' },
        { role: 'togglefullscreen' }
      ]
    }
  ]
  Menu.setApplicationMenu(Menu.buildFromTemplate(template))
}

function allowedOrigins(): Array<string | null> {
  return [startPageUrl, state.kind === 'ready' ? state.url : null]
}

function handleExternal(url: string): void {
  if (decideNavigation(url, allowedOrigins()) === 'open-external') void shell.openExternal(url)
}

function createWindow(): void {
  const window = new BrowserWindow({
    width: 1280,
    height: 860,
    minWidth: 720,
    minHeight: 480,
    show: false,
    title: 'Knowledge OS',
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true
    }
  })
  mainWindow = window
  window.on('ready-to-show', () => window.show())
  // The window shows the start page or the reader; the core has no use
  // without it, so closing the window stops the core right away.
  window.on('closed', () => {
    mainWindow = null
    openGeneration++
    stopCoreSync()
    state = { kind: 'start', recent }
  })

  const guard = (event: Electron.Event, url: string): void => {
    const decision = decideNavigation(url, allowedOrigins())
    if (decision === 'allow') return
    event.preventDefault()
    if (decision === 'open-external') void shell.openExternal(url)
  }
  window.webContents.on('will-navigate', guard)
  window.webContents.on('will-redirect', guard)
  window.webContents.setWindowOpenHandler(({ url }) => {
    handleExternal(url)
    return { action: 'deny' }
  })

  void window.loadURL(startPageUrl)
}

function isStartPage(event: IpcMainInvokeEvent): boolean {
  const url = event.senderFrame?.url ?? ''
  return decideNavigation(url, [startPageUrl]) === 'allow'
}

function handle(channel: string, action: (...args: unknown[]) => Promise<unknown>): void {
  ipcMain.handle(channel, (event, ...args) => {
    // Only the start page may use the workspace actions, never the reader UI.
    if (!isStartPage(event)) throw new Error('not allowed from this page')
    return action(...args)
  })
}

function registerIpc(): void {
  handle(IPC.getState, async () => state)
  handle(IPC.openWorkspace, () => chooseAndOpen())
  handle(IPC.createWorkspace, () => chooseAndCreate())
  handle(IPC.showStart, () => showStart())
  handle(IPC.retry, async () => {
    if (state.kind !== 'error') return
    // Python may have been installed or KOS_PYTHON fixed since the last check.
    pythonExecutable = null
    if (state.root !== null) await openWorkspace(state.root)
    else if ((await ensurePython()) !== null) await showStart()
  })
  handle(IPC.openRecent, async (root) => {
    if (typeof root !== 'string' || !recent.some((item) => item.root === root)) return
    await openWorkspace(root)
  })
}

// Stop the core on every way out of the main process. A hard crash that
// skips these handlers is covered by the core's --exit-on-stdin-eof lifeline.
process.on('exit', stopCoreSync)
for (const signal of ['SIGINT', 'SIGTERM', 'SIGHUP'] as const) {
  process.on(signal, () => {
    stopCoreSync()
    app.exit(0)
  })
}
process.on('uncaughtException', (error) => {
  stopCoreSync()
  console.error(error)
  app.exit(1)
})
app.on('will-quit', stopCoreSync)

app.whenReady().then(() => {
  session.defaultSession.setPermissionRequestHandler((_webContents, _permission, callback) =>
    callback(false)
  )
  registerIpc()
  buildMenu()
  createWindow()

  const initial = process.env['KOS_DESKTOP_WORKSPACE']
  if (initial) void openWorkspace(initial)

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})
