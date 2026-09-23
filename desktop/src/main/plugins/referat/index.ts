// The Referat plugin: start Referat from an open knowledge base and import a
// finished meeting into one of its projects. It runs the Referat SDK here in
// the main process, shows its own window with its own preload script, and
// writes only through the core's local write API. The core and the reader
// know nothing about Referat; without Referat installed the plugin shows
// that and nothing else changes.

import { BrowserWindow, dialog, ipcMain, type MenuItemConstructorOptions } from 'electron'
import type { IpcMainInvokeEvent } from 'electron'
import {
  findReferat,
  getMeeting,
  launchReferat,
  listMeetings,
  MEETING_ID_PATTERN,
  type Meeting
} from 'referat-sdk'
import {
  REFERAT_IPC,
  type ImportContext,
  type ImportRequest,
  type ImportResultView,
  type LaunchResultView,
  type MeetingListResult,
  type PreviewResult,
  type ReferatAvailability
} from '../../../shared/referat'
import { cleanFolder, RECORD_ID_PATTERN } from './ids'
import { executePlan, findExistingImport, type ImportResult } from './importer'
import { KosClient } from './kosClient'
import { buildImportPlan, DEFAULT_FOLDER, noteBaseIdFor, type ImportPlan } from './plan'
import { errorMessage, meetingPreview, meetingRow, skippedRow } from './views'

export interface ReferatHost {
  mainWindow: () => BrowserWindow | null
  /** The running core's URL while a knowledge base is open, else null. */
  coreUrl: () => string | null
  /** URL of the import window's page. */
  pageUrl: string
  /** Absolute path of the import window's preload script. */
  preloadPath: string
}

export interface ReferatPlugin {
  menu: () => MenuItemConstructorOptions
  /** Call when the open knowledge base changes or closes. */
  workspaceChanged: () => void
}

function commitLabel(result: ImportResult['created'][number]['commit']): string {
  if (result === null) return 'not reported'
  if (result.committed && result.sha) return result.sha.slice(0, 7)
  return `not committed (${result.skipped ?? 'unknown'})`
}

function resultView(result: ImportResult): ImportResultView {
  return {
    ok: true,
    created: result.created.map((record) => ({
      kind: record.kind,
      id: record.id,
      title: record.title,
      commit: commitLabel(record.commit)
    })),
    failed: result.failed,
    notAttempted: result.notAttempted,
    canRetry: result.noteId !== null && result.pending.length > 0
  }
}

async function availability(): Promise<ReferatAvailability> {
  const found = await findReferat()
  // Without an explicit data folder (REFERAT_USER_DATA), meetings are read
  // only from an installed Referat, as the SDK does.
  if (found.dataDirSource === 'default' && !found.installed) return { kind: 'not-installed' }
  if (!found.dataDirExists) return { kind: 'no-data' }
  return { kind: 'available', installed: found.installed, version: found.version }
}

export function createReferatPlugin(host: ReferatHost): ReferatPlugin {
  let window: BrowserWindow | null = null
  /** The knowledge base the import window was opened for. */
  let windowCoreUrl: string | null = null
  let client: KosClient | null = null
  let clientUrl: string | null = null
  let launchedFromProject: string | null = null
  /** Decisions that failed in the last import, with their note, for a retry. */
  let pending: { plan: ImportPlan; noteId: string; url: string } | null = null

  function kos(): KosClient {
    const url = host.coreUrl()
    if (url === null) throw new Error('No knowledge base is open.')
    if (client === null || clientUrl !== url) {
      client = new KosClient(url)
      clientUrl = url
    }
    return client
  }

  /** The project the main window shows: a project page, or a record inside a project. */
  async function currentProject(): Promise<string | null> {
    const main = host.mainWindow()
    const core = host.coreUrl()
    if (main === null || core === null) return null
    let location: URL
    try {
      location = new URL(main.webContents.getURL())
      if (location.origin !== new URL(core).origin) return null
    } catch {
      return null
    }
    const project = /^\/p\/([^/]+)/.exec(location.pathname)
    if (project) return decodeURIComponent(project[1])
    const record = /^\/r\/([^/]+)/.exec(location.pathname)
    if (record) {
      try {
        return await kos().projectOfRecord(decodeURIComponent(record[1]))
      } catch {
        return null
      }
    }
    return null
  }

  async function launch(): Promise<LaunchResultView> {
    try {
      launchedFromProject = (await currentProject()) ?? launchedFromProject
      const result = await launchReferat()
      return { ok: true, alreadyRunning: result.alreadyRunning }
    } catch (error) {
      return { ok: false, error: errorMessage(error) }
    }
  }

  async function launchFromMenu(): Promise<void> {
    const result = await launch()
    const parent = host.mainWindow()
    if (result.ok && !result.alreadyRunning) return
    const options = result.ok
      ? {
          type: 'info' as const,
          message: 'Referat is already running.',
          detail: 'Switch to Referat to record the meeting.'
        }
      : {
          type: 'warning' as const,
          message: result.error,
          detail:
            'Install Referat to record meetings. Meetings recorded with Referat can then be imported with Referat > Import Meeting from Referat.'
        }
    if (parent) await dialog.showMessageBox(parent, { ...options, title: 'Referat' })
    else await dialog.showMessageBox({ ...options, title: 'Referat' })
  }

  function openWindow(): void {
    if (window !== null && !window.isDestroyed()) {
      window.focus()
      return
    }
    const parent = host.mainWindow() ?? undefined
    const created = new BrowserWindow({
      parent,
      width: 920,
      height: 760,
      minWidth: 640,
      minHeight: 480,
      show: false,
      title: 'Import from Referat',
      autoHideMenuBar: true,
      webPreferences: {
        preload: host.preloadPath,
        contextIsolation: true,
        nodeIntegration: false,
        sandbox: true
      }
    })
    window = created
    windowCoreUrl = host.coreUrl()
    created.setMenu(null)
    created.on('ready-to-show', () => created.show())
    created.on('closed', () => {
      if (window === created) window = null
    })
    // The window shows only its own page (a reload is allowed): no other
    // navigation, no new windows.
    const ownPage = (url: string): boolean => url.split(/[?#]/)[0] === host.pageUrl
    const guard = (event: Electron.Event, url: string): void => {
      if (!ownPage(url)) event.preventDefault()
    }
    created.webContents.on('will-navigate', guard)
    created.webContents.on('will-redirect', guard)
    created.webContents.setWindowOpenHandler(() => ({ action: 'deny' }))
    void created.loadURL(host.pageUrl)
  }

  function fromImportWindow(event: IpcMainInvokeEvent): boolean {
    return window !== null && !window.isDestroyed() && event.sender === window.webContents
  }

  function handle<A extends unknown[], R>(
    channel: string,
    action: (...args: A) => Promise<R>
  ): void {
    ipcMain.handle(channel, (event, ...args) => {
      // Only the import window may call the plugin, never the reader UI.
      if (!fromImportWindow(event)) throw new Error('not allowed from this page')
      return action(...(args as A))
    })
  }

  async function readMeeting(meetingId: unknown): Promise<Meeting> {
    if (typeof meetingId !== 'string' || !MEETING_ID_PATTERN.test(meetingId)) {
      throw new Error('This is not a Referat meeting id.')
    }
    // Voice embeddings are biometric data; the SDK leaves them out by default
    // and the import never asks for them.
    return getMeeting(meetingId, { includeSpeakerEmbeddings: false })
  }

  handle(REFERAT_IPC.context, async (): Promise<ImportContext> => {
    const [state, projects] = await Promise.all([
      availability(),
      kos()
        .projects()
        .catch(() => [])
    ])
    const current = await currentProject()
    const preferred = [current, launchedFromProject].find(
      (id) => id !== null && projects.some((project) => project.id === id)
    )
    return {
      availability: state,
      projects,
      defaultProjectId: preferred ?? projects[0]?.id ?? null,
      defaultFolder: DEFAULT_FOLDER
    }
  })

  handle(REFERAT_IPC.listMeetings, async (): Promise<MeetingListResult> => {
    try {
      const { meetings, skipped } = await listMeetings()
      return { ok: true, meetings: meetings.map(meetingRow), skipped: skipped.map(skippedRow) }
    } catch (error) {
      return { ok: false, error: errorMessage(error) }
    }
  })

  handle(
    REFERAT_IPC.preview,
    async (meetingId: unknown, summaryId: unknown): Promise<PreviewResult> => {
      let meeting: Meeting
      try {
        meeting = await readMeeting(meetingId)
      } catch (error) {
        return { ok: false, error: errorMessage(error) }
      }
      if (meeting.inProgress)
        return { ok: false, error: 'Referat is still working on this meeting.' }
      try {
        const api = kos()
        const [existing, ids] = await Promise.all([
          findExistingImport(api, meeting.id, noteBaseIdFor(meeting)),
          api.recordIds()
        ])
        const preview = meetingPreview(
          meeting,
          typeof summaryId === 'string' ? summaryId : null,
          existing,
          new Set(ids)
        )
        return { ok: true, preview }
      } catch (error) {
        return { ok: false, error: error instanceof Error ? error.message : String(error) }
      }
    }
  )

  handle(REFERAT_IPC.importMeeting, async (raw: unknown): Promise<ImportResultView> => {
    const request = raw as Partial<ImportRequest> | null
    if (
      request === null ||
      typeof request !== 'object' ||
      typeof request.summaryId !== 'string' ||
      typeof request.projectId !== 'string' ||
      !RECORD_ID_PATTERN.test(request.projectId) ||
      typeof request.folder !== 'string' ||
      typeof request.includeTranscript !== 'boolean' ||
      !Array.isArray(request.decisions) ||
      !request.decisions.every((index) => Number.isInteger(index) && index >= 0)
    ) {
      return { ok: false, error: 'The import request was not understood.' }
    }
    const folder = cleanFolder(request.folder)
    if (folder === null) {
      return {
        ok: false,
        error: 'The folder must be a relative path of plain folder names, such as meeting-notes.'
      }
    }
    let meeting: Meeting
    try {
      meeting = await readMeeting(request.meetingId)
    } catch (error) {
      return { ok: false, error: errorMessage(error) }
    }
    if (meeting.inProgress) return { ok: false, error: 'Referat is still working on this meeting.' }
    try {
      const api = kos()
      const projects = await api.projects()
      if (!projects.some((project) => project.id === request.projectId)) {
        return { ok: false, error: 'That project does not exist in this knowledge base.' }
      }
      // Checked again right before writing: never import the same meeting twice.
      const existing = await findExistingImport(api, meeting.id, noteBaseIdFor(meeting))
      if (existing.length > 0) {
        return { ok: false, error: 'This meeting has already been imported.', existing }
      }
      const plan = buildImportPlan(meeting, {
        summaryId: request.summaryId,
        projectId: request.projectId,
        folder,
        includeTranscript: request.includeTranscript,
        decisions: request.decisions,
        now: new Date()
      })
      const result = await executePlan(api, plan)
      pending =
        result.noteId !== null && result.pending.length > 0
          ? {
              plan: { ...plan, decisions: result.pending },
              noteId: result.noteId,
              url: host.coreUrl() ?? ''
            }
          : null
      return resultView(result)
    } catch (error) {
      return { ok: false, error: error instanceof Error ? error.message : String(error) }
    }
  })

  handle(REFERAT_IPC.retryFailed, async (): Promise<ImportResultView> => {
    const retry = pending
    if (retry === null || retry.url !== host.coreUrl()) {
      return { ok: false, error: 'There is nothing to retry.' }
    }
    try {
      const result = await executePlan(kos(), retry.plan, retry.noteId)
      pending =
        result.pending.length > 0
          ? { ...retry, plan: { ...retry.plan, decisions: result.pending } }
          : null
      return resultView(result)
    } catch (error) {
      return { ok: false, error: error instanceof Error ? error.message : String(error) }
    }
  })

  handle(REFERAT_IPC.launch, () => launch())

  handle(REFERAT_IPC.openRecord, async (id: unknown): Promise<void> => {
    const core = host.coreUrl()
    const main = host.mainWindow()
    if (typeof id !== 'string' || !RECORD_ID_PATTERN.test(id) || core === null || main === null) {
      return
    }
    await main.loadURL(`${core.replace(/\/+$/, '')}/r/${id}`)
    main.focus()
    window?.close()
  })

  handle(REFERAT_IPC.close, async (): Promise<void> => {
    window?.close()
  })

  return {
    menu: () => {
      const open = host.coreUrl() !== null
      return {
        label: 'Referat',
        submenu: [
          {
            label: 'Record Meeting with Referat',
            enabled: open,
            click: () => void launchFromMenu()
          },
          {
            label: 'Import Meeting from Referat…',
            enabled: open,
            click: () => openWindow()
          }
        ]
      }
    },
    workspaceChanged: () => {
      if (pending !== null && pending.url !== host.coreUrl()) pending = null
      // The window belongs to one knowledge base; close it when that one closes or changes.
      if (window !== null && !window.isDestroyed() && windowCoreUrl !== host.coreUrl()) {
        window.close()
      }
    }
  }
}
