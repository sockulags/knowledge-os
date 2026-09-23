// IPC between the Referat import window and the main process. The window
// gets only these calls; the SDK, the file system, and the core's write
// token stay in the main process. No value here carries a file path.

export const REFERAT_IPC = {
  context: 'referat:context',
  listMeetings: 'referat:list-meetings',
  preview: 'referat:preview',
  importMeeting: 'referat:import',
  retryFailed: 'referat:retry-failed',
  launch: 'referat:launch',
  openRecord: 'referat:open-record',
  close: 'referat:close'
} as const

/** Whether meetings can be read at all. */
export type ReferatAvailability =
  | { kind: 'available'; installed: boolean; version: string | null }
  | { kind: 'not-installed' }
  | { kind: 'no-data' }

export interface ProjectOption {
  id: string
  title: string
}

export interface ImportContext {
  availability: ReferatAvailability
  projects: ProjectOption[]
  /** The project shown in the main window, else the one Referat was last started from. */
  defaultProjectId: string | null
  defaultFolder: string
}

export interface MeetingRow {
  id: string
  title: string
  held: string
  duration: string
  status: string
  inProgress: boolean
  importable: boolean
  /** Why the meeting cannot be imported, when it cannot. */
  reason: string | null
}

export interface SkippedRow {
  id: string
  error: string
}

export type MeetingListResult =
  { ok: true; meetings: MeetingRow[]; skipped: SkippedRow[] } | { ok: false; error: string }

export interface SummaryOption {
  id: string
  label: string
}

export interface DecisionOption {
  index: number
  title: string
  markdown: string
}

export interface ExistingRecord {
  id: string
  title: string
  isDecision: boolean
}

export interface MeetingPreview {
  id: string
  title: string
  held: string
  duration: string
  summaries: SummaryOption[]
  summaryId: string
  found: { summary: boolean; decisions: boolean; actionItems: boolean; openQuestions: boolean }
  decisions: DecisionOption[]
  transcriptSegments: number
  /** The note's id if nothing takes it first. */
  noteId: string
  /** The note as it would be written, without a transcript. */
  noteMarkdown: string
  /** Records that already carry this meeting's provenance. */
  existing: ExistingRecord[]
}

export type PreviewResult = { ok: true; preview: MeetingPreview } | { ok: false; error: string }

export interface ImportRequest {
  meetingId: string
  summaryId: string
  projectId: string
  folder: string
  includeTranscript: boolean
  decisions: number[]
}

export interface ImportedRecord {
  kind: 'note' | 'decision'
  id: string
  title: string
  /** Short commit hash, or why nothing was committed. */
  commit: string
}

export interface NotImportedRecord {
  kind: 'note' | 'decision'
  title: string
  error: string
  detail: string
}

export type ImportResultView =
  | {
      ok: true
      created: ImportedRecord[]
      failed: NotImportedRecord[]
      notAttempted: NotImportedRecord[]
      canRetry: boolean
    }
  | { ok: false; error: string; existing?: ExistingRecord[] }

export type LaunchResultView = { ok: true; alreadyRunning: boolean } | { ok: false; error: string }

/** The API the import window's preload script exposes as `window.referat`. */
export interface ReferatApi {
  context: () => Promise<ImportContext>
  listMeetings: () => Promise<MeetingListResult>
  preview: (meetingId: string, summaryId: string | null) => Promise<PreviewResult>
  importMeeting: (request: ImportRequest) => Promise<ImportResultView>
  retryFailed: () => Promise<ImportResultView>
  launch: () => Promise<LaunchResultView>
  openRecord: (id: string) => Promise<void>
  close: () => Promise<void>
}
