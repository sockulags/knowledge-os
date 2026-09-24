// Electron main process: one window that shows either the start page (pick,
// create, or reopen a workspace; errors) or the reader UI served by the Python
// core for the open workspace.

import { app, BrowserWindow, dialog, ipcMain, Menu, nativeTheme, session, shell } from 'electron'
import type { IpcMainInvokeEvent, MenuItemConstructorOptions } from 'electron'
import { existsSync, statSync } from 'fs'
import { basename, join } from 'path'
import { pathToFileURL } from 'url'
import { IPC, type RecentWorkspace, type ShellState } from '../shared/types'
import appIcon from '../../build/icon.ico?asset'
import { decideNavigation } from './navigation'
import { createReferatPlugin, type ReferatPlugin } from './plugins/referat'
import {
  CoreProcess,
  initWorkspace,
  pythonEnvironment,
  resolvePython,
  type CoreFailure
} from './pythonCore'
import { bundledCore, findRepoRoot, interpreterCandidates } from './pythonInterpreter'
import { addRecent, loadRecent, saveRecent } from './recentWorkspaces'
import { decideStartup, notAKnowledgeBaseNotice, type PathKind } from './reopen'
import {
  fetchWriteToken,
  removeRuntimeFile,
  runtimeFilePath,
  writeRuntimeFile
} from './runtimeFile'
import { loadSettings, saveSettings, type AppSettings } from './settings'
import type { UpdateNotice } from './updateFlow'
import {
  checkForUpdatesManually,
  initUpdater,
  installDownloadedUpdate,
  updateState,
  updatesSupported
} from './updater'

// Development and test hook: keep this run's settings apart from others.
if (process.env['KOS_DESKTOP_USER_DATA']) {
  app.setPath('userData', process.env['KOS_DESKTOP_USER_DATA'])
}

const repoRoot = findRepoRoot(app.getAppPath(), existsSync)
const pythonEnv = pythonEnvironment(process.env, repoRoot)
const recentFile = join(app.getPath('userData'), 'recent-workspaces.json')
const settingsFile = join(app.getPath('userData'), 'settings.json')
const runtimeFile = runtimeFilePath(app.getPath('userData'))

let mainWindow: BrowserWindow | null = null
let core: CoreProcess | null = null
let pythonExecutable: string | null = null
let recent: RecentWorkspace[] = loadRecent(recentFile)
let settings: AppSettings = loadSettings(settingsFile)
let state: ShellState = { kind: 'start', recent }
/** Set by "Restart to update" until the window closes or the person keeps editing. */
let restartPending = false
/** Increments per open request so a slow, superseded start is discarded. */
let openGeneration = 0
/** The optional Referat plugin, created once the app is ready. */
let referat: ReferatPlugin | null = null
/** The core process id the runtime file for agents currently describes, if any. */
let publishedCorePid: number | null = null

const startPageUrl =
  !app.isPackaged && process.env['ELECTRON_RENDERER_URL']
    ? process.env['ELECTRON_RENDERER_URL']
    : pathToFileURL(join(__dirname, '../renderer/index.html')).href
const referatPageUrl =
  !app.isPackaged && process.env['ELECTRON_RENDERER_URL']
    ? `${process.env['ELECTRON_RENDERER_URL'].replace(/\/+$/, '')}/referat.html`
    : pathToFileURL(join(__dirname, '../renderer/referat.html')).href

function stopCoreSync(): void {
  unpublishRuntime()
  core?.stopSync()
  core = null
}

/**
 * Tell agents where the open knowledge base's core listens: `kos mcp` reads
 * the runtime file on every tool call (see runtimeFile.ts). Failing to write
 * it only means agents report that the app is not open.
 */
async function publishRuntime(started: CoreProcess, root: string): Promise<void> {
  const pid = started.pid
  if (pid === undefined) return
  try {
    const writeToken = await fetchWriteToken(started.url)
    if (core !== started) return
    writeRuntimeFile(runtimeFile, {
      port: Number(new URL(started.url).port),
      writeToken,
      workspaceRoot: root,
      workspaceName: started.name || basename(root),
      appVersion: app.getVersion(),
      corePid: pid
    })
    publishedCorePid = pid
  } catch (error) {
    console.error('could not write the runtime file for agents', error)
  }
}

function unpublishRuntime(): void {
  if (publishedCorePid === null) return
  removeRuntimeFile(runtimeFile, publishedCorePid)
  publishedCorePid = null
}

function setState(next: ShellState): void {
  state = next
  const window = mainWindow
  if (window === null || window.isDestroyed()) return
  if (next.kind === 'ready') {
    // A reasonable title for the moment before the reader has loaded and
    // read its own nav payload; the reader then takes over (see
    // reader-ui/src/hooks/useDocumentTitle.ts) and keeps it in the same
    // "<page> — <workspace> — Knowledge OS" shape, refined with the current
    // page's own title. Electron mirrors the window title from the page's
    // `document.title` by default, so nothing here needs to intercept that.
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
  referat?.workspaceChanged()
  buildMenu()
}

function showError(root: string | null, failure: CoreFailure): void {
  setState({ kind: 'error', root, ...failure, recent })
}

async function ensurePython(): Promise<string | null> {
  if (pythonExecutable !== null) return pythonExecutable
  const bundled = bundledCore({
    env: process.env,
    packaged: app.isPackaged,
    resourcesPath: process.resourcesPath,
    platform: process.platform
  })
  if (bundled !== null) {
    if (!existsSync(bundled)) {
      showError(null, {
        error: 'core-missing',
        message: 'The Knowledge OS core is missing from this installation. Reinstall the app.',
        detail: `Not found: ${bundled}`
      })
      return null
    }
    pythonExecutable = bundled
    return pythonExecutable
  }
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

/**
 * Open `root`. `reopened` is the recent entry when this is the knowledge base
 * reopened on start: if the core then says the folder is not a knowledge
 * base, the start page shows that as a one-line reason instead of the error
 * screen. Every other failure shows the error screen.
 */
async function openWorkspace(root: string, reopened: RecentWorkspace | null = null): Promise<void> {
  const generation = ++openGeneration
  const previous = core
  core = null
  unpublishRuntime()
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
    if (reopened !== null && result.failure.error === 'invalid-workspace') {
      console.error('could not reopen the last knowledge base:', result.failure.message)
      setState({ kind: 'start', recent, notice: notAKnowledgeBaseNotice(reopened) })
    } else {
      showError(root, result.failure)
    }
    return
  }

  core = result.core
  const started = result.core
  started.onUnexpectedExit((detail) => {
    if (core !== started) return
    core = null
    unpublishRuntime()
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
  void publishRuntime(started, root)
}

async function showStart(): Promise<void> {
  openGeneration++
  const previous = core
  core = null
  unpublishRuntime()
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

function changeSettings(change: Partial<AppSettings>): void {
  settings = { ...settings, ...change }
  try {
    saveSettings(settingsFile, settings)
  } catch (error) {
    console.error('could not save the settings', error)
  }
  buildMenu()
}

/**
 * Restart into the downloaded update. Closing the window goes through the
 * same unsaved-changes question as any other close; the install only starts
 * once the window has actually closed, which also stops the core.
 */
function restartToUpdate(): void {
  const window = mainWindow
  if (window === null || window.isDestroyed()) {
    stopCoreSync()
    installDownloadedUpdate()
    return
  }
  restartPending = true
  window.close()
}

function showUpdateNotice(notice: UpdateNotice): void {
  const window = mainWindow
  if (window === null || window.isDestroyed()) return
  if (notice.kind === 'message') {
    void dialog.showMessageBox(window, {
      type: 'info',
      title: 'Software update',
      message: notice.message,
      detail: notice.detail
    })
    return
  }
  void dialog
    .showMessageBox(window, {
      type: 'info',
      buttons: ['Restart to update', 'Later'],
      defaultId: 0,
      cancelId: 1,
      title: 'Update ready',
      message: `Knowledge OS ${notice.version} is ready to install.`,
      detail:
        'Restart now to update, or later from Help → Restart to Update. ' +
        'It is also installed the next time you quit.'
    })
    .then(({ response }) => {
      if (response === 0) restartToUpdate()
    })
}

function helpMenu(): MenuItemConstructorOptions {
  const update = updateState()
  const items: MenuItemConstructorOptions[] = [
    { label: 'Check for Updates…', click: () => checkForUpdatesManually() },
    {
      label: 'Check for Updates Automatically',
      type: 'checkbox',
      checked: settings.checkForUpdates,
      enabled: updatesSupported(),
      click: (item) => changeSettings({ checkForUpdates: item.checked })
    }
  ]
  if (update.phase === 'ready') {
    items.push(
      { type: 'separator' },
      { label: `Restart to Update (${update.version})`, click: () => restartToUpdate() }
    )
  }
  return { label: 'Help', submenu: items }
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
        {
          label: 'Reopen the Last Knowledge Base on Start',
          type: 'checkbox',
          checked: settings.reopenLastWorkspace,
          click: (item) => changeSettings({ reopenLastWorkspace: item.checked })
        },
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
    },
    ...(referat !== null ? [referat.menu()] : []),
    helpMenu()
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
    icon: appIcon,
    // The start page's paper tone, so the window never flashes white first.
    backgroundColor: nativeTheme.shouldUseDarkColors ? '#15181b' : '#fbfaf7',
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
    if (restartPending) {
      restartPending = false
      installDownloadedUpdate()
    }
  })

  const guard = (event: Electron.Event, url: string): void => {
    const decision = decideNavigation(url, allowedOrigins())
    if (decision === 'allow') return
    event.preventDefault()
    if (decision === 'open-external') void shell.openExternal(url)
  }
  // The reader's editor cancels `beforeunload` while it has unsaved changes.
  // Electron then keeps the page without asking, so ask here: on window
  // close, quit, or reload, the person decides whether to discard the edits.
  window.webContents.on('will-prevent-unload', (event) => {
    const choice = dialog.showMessageBoxSync(window, {
      type: 'warning',
      buttons: ['Discard changes', 'Keep editing'],
      defaultId: 1,
      cancelId: 1,
      title: 'Unsaved changes',
      message: 'You have changes that are not saved.',
      detail: 'Leaving now discards them.'
    })
    if (choice === 0) event.preventDefault()
    // Keeping the edits also cancels a pending "Restart to update".
    else restartPending = false
  })
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

function pathKind(path: string): PathKind {
  try {
    return statSync(path).isDirectory() ? 'directory' : 'file'
  } catch {
    return 'missing'
  }
}

/** Open the requested or the last knowledge base, or say on the start page why not. */
function startup(): void {
  const decision = decideStartup({
    explicit: process.env['KOS_DESKTOP_WORKSPACE'] || null,
    reopenEnabled: settings.reopenLastWorkspace,
    recent,
    pathKind
  })
  if (decision.kind === 'open') {
    void openWorkspace(decision.root, decision.reopened ? (recent[0] ?? null) : null)
  } else if (decision.notice !== null) {
    setState({ kind: 'start', recent, notice: decision.notice })
  }
}

app.whenReady().then(() => {
  session.defaultSession.setPermissionRequestHandler((_webContents, _permission, callback) =>
    callback(false)
  )
  registerIpc()
  initUpdater({
    autoCheckEnabled: () => settings.checkForUpdates,
    notify: showUpdateNotice,
    changed: buildMenu
  })
  referat = createReferatPlugin({
    mainWindow: () => mainWindow,
    coreUrl: () => (state.kind === 'ready' ? state.url : null),
    pageUrl: referatPageUrl,
    preloadPath: join(__dirname, '../preload/referat.js')
  })
  buildMenu()
  createWindow()

  startup()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})
