// Electron main process: one window that shows either the start page (pick,
// create, or reopen a workspace; errors) or the reader UI served by the Python
// core for the open workspace. The window's frame, menu, notices, and dialogs
// are the shell's own (see windowChrome.ts).

import { app, BrowserWindow, dialog, ipcMain, Menu, nativeTheme, session, shell } from 'electron'
import type { IpcMainEvent, IpcMainInvokeEvent } from 'electron'
import { existsSync, statSync } from 'fs'
import { basename, join } from 'path'
import { pathToFileURL } from 'url'
import { SHELL_TEXT } from '../shared/shellText'
import { IPC, type RecentWorkspace, type ShellState } from '../shared/types'
import appIcon from '../../build/icon.ico?asset'
import {
  LeaveGuard,
  UNSAVED_ACTION,
  UPDATE_ACTION,
  unsavedChangesDialog,
  updateNotice
} from './chromeState'
import { createCloneWindow, type CloneWindow } from './cloneWindow'
import { flushReaderActions } from './flushReader'
import {
  buildMenus,
  COMMAND,
  menuViews,
  nativeTemplate,
  recentIndex,
  type MenuSpec
} from './menuModel'
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
import { loadSettings, saveSettings, sidebarWidth, type AppSettings } from './settings'
import type { UpdateNotice } from './updateFlow'
import {
  checkForUpdatesManually,
  initUpdater,
  installDownloadedUpdate,
  updateState,
  updatesSupported
} from './updater'
import { framedWindowOptions, MainWindowChrome, systemTheme } from './windowChrome'

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
/** Set once quitting starts, so a close held back to flush the reader resumes the quit. */
let quitRequested = false
/** Increments per open request so a slow, superseded start is discarded. */
let openGeneration = 0
/** The optional Referat plugin, created once the app is ready. */
let referat: ReferatPlugin | null = null
/** The Clone Knowledge Base window, created once the app is ready. */
let cloneWindow: CloneWindow | null = null
/** The core process id the runtime file for agents currently describes, if any. */
let publishedCorePid: number | null = null
/** The main window's title bar, menu, notices, and dialogs, created once the app is ready. */
let chrome: MainWindowChrome | null = null
/** Set once closing the window has passed the unsaved-changes question. */
let closeConfirmed = false
/** The core URL of the last reader the window was sent to, for the chrome's IPC. */
let readerUrl: string | null = null

/**
 * Whether the reader holds unsaved edits: its editor cancels `beforeunload`
 * then, so a synthetic one tells without leaving the page. Only the reader
 * is asked; the start page never holds edits.
 */
async function readerHasUnsavedChanges(): Promise<boolean> {
  const window = mainWindow
  if (window === null || window.isDestroyed()) return false
  const url = window.webContents.getURL()
  if (url === '' || decideNavigation(url, [startPageUrl]) === 'allow') return false
  const probe = `(() => {
    const event = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(event)
    return event.defaultPrevented
  })()`
  const answer = window.webContents.executeJavaScript(probe).then((value) => value === true)
  const timeout = new Promise<boolean>((resolve) => setTimeout(() => resolve(false), 1500))
  return Promise.race([answer, timeout])
}

/** Asks before anything leaves the page while the reader holds unsaved edits. */
const leaveGuard = new LeaveGuard({
  hasUnsavedChanges: readerHasUnsavedChanges,
  ask: () => chrome?.ask(unsavedChangesDialog) ?? Promise.resolve(UNSAVED_ACTION.keep)
})

/** Keeping the edits also cancels a pending "Restart to update" or quit. */
function keepEditing(): void {
  restartPending = false
  quitRequested = false
  closeConfirmed = false
}

/** Shows `url` in the main window once unsaved edits are dealt with; false when they were kept. */
async function navigateMain(url: string): Promise<boolean> {
  let went = false
  await leaveGuard.leave(() => {
    went = true
    const window = mainWindow
    // A load the page still cancels is answered in 'will-prevent-unload'.
    if (window !== null && !window.isDestroyed()) window.loadURL(url).catch(() => undefined)
  }, keepEditing)
  return went
}

const startPageUrl =
  !app.isPackaged && process.env['ELECTRON_RENDERER_URL']
    ? process.env['ELECTRON_RENDERER_URL']
    : pathToFileURL(join(__dirname, '../renderer/index.html')).href
const referatPageUrl =
  !app.isPackaged && process.env['ELECTRON_RENDERER_URL']
    ? `${process.env['ELECTRON_RENDERER_URL'].replace(/\/+$/, '')}/referat.html`
    : pathToFileURL(join(__dirname, '../renderer/referat.html')).href
const clonePageUrl =
  !app.isPackaged && process.env['ELECTRON_RENDERER_URL']
    ? `${process.env['ELECTRON_RENDERER_URL'].replace(/\/+$/, '')}/clone.html`
    : pathToFileURL(join(__dirname, '../renderer/clone.html')).href

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
    window.setTitle(`${next.name || basename(next.root)} — ${SHELL_TEXT.appName}`)
    readerUrl = next.url
    void navigateMain(next.url)
  } else {
    window.setTitle(SHELL_TEXT.appName)
    if (decideNavigation(window.webContents.getURL(), [startPageUrl]) === 'allow') {
      window.webContents.send(IPC.stateChanged, next)
    } else {
      void navigateMain(startPageUrl)
    }
  }
  chrome?.setWorkspace(next.kind === 'ready' ? next.name || basename(next.root) : null)
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
  // Before the open knowledge base's core stops: first its editor's unsaved
  // edits, then the decision actions still waiting for Undo.
  if (!(await leaveGuard.confirm())) {
    keepEditing()
    return
  }
  if (state.kind === 'ready') await flushReaderActions(mainWindow)
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
  if (!(await leaveGuard.confirm())) {
    keepEditing()
    return
  }
  if (state.kind === 'ready') await flushReaderActions(mainWindow)
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
  if (!(await leaveGuard.confirm())) {
    keepEditing()
    return
  }
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

/** Update news is a quiet notice under the title bar, never a modal box. */
function showUpdateNotice(notice: UpdateNotice): void {
  chrome?.showNotice(updateNotice(notice), (action) => {
    if (action === UPDATE_ACTION.restart) restartToUpdate()
  })
}

function setZoomLevel(level: (current: number) => number): void {
  const window = mainWindow
  if (window === null || window.isDestroyed()) return
  window.webContents.setZoomLevel(level(window.webContents.getZoomLevel()))
  chrome?.refreshZoom()
}

/** Runs a command from the in-app menu, its keyboard shortcut, or the native menu on macOS. */
function runCommand(command: string): void {
  const window = mainWindow
  const index = recentIndex(command)
  if (index !== null) {
    const item = recent[index]
    if (item !== undefined) void openWorkspace(item.root)
    return
  }
  switch (command) {
    case COMMAND.open:
      return void chooseAndOpen()
    case COMMAND.create:
      return void chooseAndCreate()
    case COMMAND.clone:
      return cloneWindow?.show()
    case COMMAND.reopenOnStart:
      return changeSettings({ reopenLastWorkspace: !settings.reopenLastWorkspace })
    case COMMAND.close:
      if (state.kind === 'ready') void showStart()
      return
    case COMMAND.exit:
      return app.quit()
    case COMMAND.reload:
      if (window !== null && !window.isDestroyed()) {
        void leaveGuard.leave(() => window.webContents.reload(), keepEditing)
      }
      return
    case COMMAND.devTools:
      return window?.webContents.toggleDevTools()
    case COMMAND.resetZoom:
      return setZoomLevel(() => 0)
    case COMMAND.zoomIn:
      return setZoomLevel((level) => level + 0.5)
    case COMMAND.zoomOut:
      return setZoomLevel((level) => level - 0.5)
    case COMMAND.fullScreen:
      return window?.setFullScreen(!window.isFullScreen())
    case COMMAND.checkForUpdates:
      return checkForUpdatesManually()
    case COMMAND.checkAutomatically:
      if (updatesSupported()) changeSettings({ checkForUpdates: !settings.checkForUpdates })
      return
    case COMMAND.restartToUpdate:
      if (updateState().phase === 'ready') restartToUpdate()
      return
    default:
      referat?.run(command)
  }
}

function currentMenus(): MenuSpec[] {
  const update = updateState()
  return buildMenus({
    recent,
    reopenLastWorkspace: settings.reopenLastWorkspace,
    workspaceOpen: state.kind === 'ready',
    checkForUpdates: settings.checkForUpdates,
    updatesSupported: updatesSupported(),
    updateReadyVersion: update.phase === 'ready' ? update.version : null,
    pluginMenus: referat !== null ? [referat.menu()] : []
  })
}

/**
 * Rebuilds the menu after anything it shows changed. The title bar draws
 * it; macOS also gets it as the native application menu, where the system
 * expects one. On Windows the native menu bar is gone and the title bar's
 * menu runs the shortcuts (see windowChrome.ts).
 */
function buildMenu(): void {
  const menus = currentMenus()
  const mac = process.platform === 'darwin'
  chrome?.setMenus(menus, menuViews(menus, mac))
  const update = updateState()
  chrome?.setTitleAction(
    update.phase === 'ready'
      ? { command: COMMAND.restartToUpdate, label: SHELL_TEXT.titleBar.updateReady }
      : null
  )
  if (mac) Menu.setApplicationMenu(Menu.buildFromTemplate(nativeTemplate(menus, runCommand)))
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
    title: SHELL_TEXT.appName,
    icon: appIcon,
    // The start page's paper tone, so the window never flashes white first.
    backgroundColor: nativeTheme.shouldUseDarkColors ? '#15181b' : '#fbfaf7',
    ...framedWindowOptions(systemTheme()),
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true
    }
  })
  mainWindow = window
  closeConfirmed = false
  chrome?.attach(window)
  window.on('ready-to-show', () => window.show())
  // Every close (the window's close button, Alt+F4, File → Exit, quitting,
  // Restart to update) first deals with unsaved edits in the reader; keeping
  // them keeps the window and cancels a pending restart or quit. Then the
  // reader writes the decision actions still waiting for Undo, and only then
  // does the window close for real (which stops the core, and afterwards
  // starts a pending update's installer).
  let closing = false
  window.on('close', (event) => {
    if (closeConfirmed) return
    event.preventDefault()
    if (closing) return
    closing = true
    void leaveGuard.leave(
      () => {
        const flushed = state.kind === 'ready' ? flushReaderActions(window) : Promise.resolve()
        void flushed.finally(() => {
          closing = false
          if (window.isDestroyed()) return
          closeConfirmed = true
          if (quitRequested) app.quit()
          else window.close()
        })
      },
      () => {
        closing = false
        keepEditing()
      }
    )
  })
  // The window shows the start page or the reader; the core has no use
  // without it, so closing the window stops the core right away.
  window.on('closed', () => {
    mainWindow = null
    leaveGuard.reset()
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
  // The reader's editor cancels `beforeunload` while it has unsaved changes,
  // and Electron then keeps the page. The leave guard has normally asked
  // already and lets a confirmed discard through; otherwise the page stays,
  // and the question is asked for the attempt that was cancelled.
  window.webContents.on('will-prevent-unload', (event) => {
    const { allow, retry } = leaveGuard.unloadPrevented()
    if (allow) {
      event.preventDefault()
      return
    }
    closeConfirmed = false
    if (retry !== null) void leaveGuard.leave(retry, keepEditing, true)
    else keepEditing()
  })
  window.webContents.on('did-navigate', () => leaveGuard.reset())
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

function isReaderPage(event: IpcMainEvent): boolean {
  if (state.kind !== 'ready') return false
  const url = event.senderFrame?.url ?? ''
  return decideNavigation(url, [state.url]) === 'allow'
}

function registerIpc(): void {
  // The reader keeps its sidebar width here: it runs on a new port each
  // launch, so its own browser storage would not survive a restart.
  ipcMain.on(IPC.getSidebarWidth, (event) => {
    event.returnValue = isReaderPage(event) ? settings.readerSidebarWidth : null
  })
  ipcMain.on(IPC.setSidebarWidth, (event, width: unknown) => {
    if (!isReaderPage(event)) return
    const next = sidebarWidth(width)
    if (next === settings.readerSidebarWidth) return
    settings = { ...settings, readerSidebarWidth: next }
    try {
      saveSettings(settingsFile, settings)
    } catch (error) {
      console.error('could not save the settings', error)
    }
  })
  handle(IPC.getState, async () => state)
  handle(IPC.openWorkspace, () => chooseAndOpen())
  handle(IPC.createWorkspace, () => chooseAndCreate())
  handle(IPC.cloneWorkspace, async () => cloneWindow?.show())
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
app.on('before-quit', () => {
  quitRequested = true
})
app.on('will-quit', () => {
  cloneWindow?.cancelRunning()
  stopCoreSync()
})

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
  // Windows and Linux get no native menu bar: the title bar draws the menu.
  if (process.platform !== 'darwin') Menu.setApplicationMenu(null)
  chrome = new MainWindowChrome({
    // The reader stays allowed after its core stopped, so it can still
    // answer the unsaved-changes question before the error screen replaces it.
    allowedPage: (url) => decideNavigation(url, [startPageUrl, readerUrl]) === 'allow',
    command: runCommand
  })
  initUpdater({
    autoCheckEnabled: () => settings.checkForUpdates,
    notify: showUpdateNotice,
    changed: buildMenu
  })
  referat = createReferatPlugin({
    mainWindow: () => mainWindow,
    coreUrl: () => (state.kind === 'ready' ? state.url : null),
    pageUrl: referatPageUrl,
    preloadPath: join(__dirname, '../preload/referat.js'),
    notify: (notice) => chrome?.showNotice({ key: 'referat', actions: [], ...notice }),
    navigateMain
  })
  cloneWindow = createCloneWindow({
    mainWindow: () => mainWindow,
    pageUrl: clonePageUrl,
    preloadPath: join(__dirname, '../preload/clone.js'),
    defaultParent: () => join(app.getPath('documents'), 'Knowledge bases'),
    python: ensurePython,
    pythonEnv,
    open: (root) => openWorkspace(root)
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
