// Updates from GitHub releases through electron-updater.
//
// The installed app checks shortly after startup and every few hours while the
// "check automatically" setting is on, and whenever the person picks Help →
// Check for Updates…. A found update downloads in the background. Once it is
// downloaded the person is offered "Restart to update"; the app never restarts
// on its own. Failures of automatic checks (offline, GitHub unreachable, no
// release metadata) are logged and never shown; a manual check reports them in
// one short message.
//
// The installer is unsigned. electron-updater only verifies the Authenticode
// publisher when app-update.yml names a `publisherName`, which electron-builder
// writes only for signed builds, so with no signing configuration there is no
// publisher check. What still protects the download is the sha512 from
// latest.yml, fetched over HTTPS from the GitHub release, which the installer
// must match before it is run.

import { app } from 'electron'
import { autoUpdater } from 'electron-updater'
import {
  INITIAL_UPDATE_STATE,
  canRestartToUpdate,
  nextUpdateState,
  testFeedUrl,
  type UpdateEvent,
  type UpdateNotice,
  type UpdateState
} from './updateFlow'

const FIRST_CHECK_DELAY_MS = 10_000
const RECHECK_INTERVAL_MS = 4 * 60 * 60 * 1000

export interface UpdaterHooks {
  /** Whether automatic checks are on; read at every scheduled check. */
  autoCheckEnabled: () => boolean
  /** Shows a notice; `ready` notices offer "Restart to update". */
  notify: (notice: UpdateNotice) => void
  /** Called after every state change, e.g. to rebuild the menu. */
  changed: () => void
}

let state: UpdateState = INITIAL_UPDATE_STATE
let hooks: UpdaterHooks | null = null
let active = false

function log(text: string, error?: unknown): void {
  if (error !== undefined) console.error(`[updater] ${text}`, error)
  else console.log(`[updater] ${text}`)
}

function dispatch(event: UpdateEvent): void {
  const result = nextUpdateState(state, event, app.getVersion())
  state = result.state
  if (result.notice !== null) hooks?.notify(result.notice)
  hooks?.changed()
  if (result.startCheck) {
    // Errors also arrive through the 'error' event, which dispatches 'failed'.
    autoUpdater.checkForUpdates().catch((error) => log('check failed', error))
  }
}

/** Whether this build can update itself: only the packaged app has an installer to replace. */
export function updatesSupported(): boolean {
  return active
}

export function updateState(): UpdateState {
  return state
}

/**
 * Wires up electron-updater. It stays inactive when the app is not packaged:
 * there is no app-update.yml to read and no installation to replace.
 */
export function initUpdater(options: UpdaterHooks): void {
  hooks = options
  if (!app.isPackaged) {
    log('inactive: the app is not packaged')
    return
  }
  active = true
  autoUpdater.autoDownload = true
  // A downloaded update is also installed silently when the app quits normally.
  autoUpdater.autoInstallOnAppQuit = true
  autoUpdater.logger = {
    info: (text: unknown) => log(String(text)),
    warn: (text: unknown) => log(String(text)),
    error: (text: unknown) => log('error', text),
    debug: () => undefined
  }

  // Local update tests only; see "Testing an update locally" in desktop/README.md.
  const feed = testFeedUrl(import.meta.env.MAIN_VITE_KOS_UPDATE_TEST_FEED)
  if (feed !== null) {
    log(`using the local test feed ${feed}`)
    autoUpdater.setFeedURL({ provider: 'generic', url: feed })
  }

  autoUpdater.on('update-available', (info) =>
    dispatch({ type: 'available', version: info.version })
  )
  autoUpdater.on('update-not-available', () => dispatch({ type: 'not-available' }))
  autoUpdater.on('update-downloaded', (info) =>
    dispatch({ type: 'downloaded', version: info.version })
  )
  autoUpdater.on('error', (error) => {
    log('update failed', error)
    dispatch({ type: 'failed' })
  })

  const scheduled = (): void => {
    if (options.autoCheckEnabled()) dispatch({ type: 'check', manual: false })
  }
  setTimeout(scheduled, FIRST_CHECK_DELAY_MS)
  setInterval(scheduled, RECHECK_INTERVAL_MS)
}

/** Help → Check for Updates…: always reports its outcome. */
export function checkForUpdatesManually(): void {
  if (!active) {
    hooks?.notify({
      kind: 'message',
      message: 'Updates are only available in the installed app.'
    })
    return
  }
  dispatch({ type: 'check', manual: true })
}

/**
 * Runs the downloaded installer and quits. The caller must already have closed
 * the window (so unsaved edits were confirmed) and stopped the core.
 */
export function installDownloadedUpdate(): void {
  if (!canRestartToUpdate(state)) return
  log('installing the downloaded update and restarting')
  try {
    // Silent install, then start the updated app.
    autoUpdater.quitAndInstall(true, true)
  } catch (error) {
    log('could not start the installer', error)
  }
}
