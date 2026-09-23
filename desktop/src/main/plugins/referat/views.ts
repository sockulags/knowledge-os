// Shapes SDK results into what the import window shows. Nothing here passes
// on a file path: meeting folders, audio files, and the data folder stay in
// the main process, and error messages name a file by its base name only.

import type { Meeting, MeetingListItem, SkippedMeeting } from 'referat-sdk'
import type {
  ExistingRecord,
  MeetingPreview,
  MeetingRow,
  SkippedRow
} from '../../../shared/referat'
import { uniqueId } from './ids'
import {
  buildImportPlan,
  decisionCandidates,
  defaultSummary,
  findSummary,
  formatDuration,
  formatMeetingTime,
  noteTitle,
  summaryLabel
} from './plan'
import { parseSummary } from './sections'

const STATUS_LABELS: Record<MeetingListItem['status'], string> = {
  recording: 'Recording',
  recorded: 'Waiting to be processed',
  transcribing: 'Transcribing',
  diarizing: 'Identifying speakers',
  summarizing: 'Writing minutes',
  done: 'Finished',
  error: 'Failed'
}

export function meetingRow(item: MeetingListItem): MeetingRow {
  let reason: string | null = null
  if (item.inProgress) reason = 'Referat is still working on this meeting.'
  else if (item.artifacts.summaries === 0) {
    reason =
      item.status === 'error' && item.error
        ? `Referat could not finish it: ${item.error.message}`
        : 'It has no minutes.'
  }
  return {
    id: item.id,
    title: item.title.trim() || 'Untitled meeting',
    held: formatMeetingTime(item.createdAt),
    duration: formatDuration(item.durationSec),
    status: STATUS_LABELS[item.status] ?? item.status,
    inProgress: item.inProgress,
    importable: reason === null,
    reason
  }
}

function baseName(file: string): string {
  return file.split(/[\\/]/).pop() ?? file
}

interface ReferatErrorLike {
  code?: unknown
  file?: unknown
  issues?: unknown
}

/** A message about an SDK error that does not reveal where Referat keeps its files. */
export function errorMessage(error: unknown): string {
  const code = (error as ReferatErrorLike | null)?.code
  switch (code) {
    case 'REFERAT_NOT_INSTALLED':
      return 'Referat is not installed.'
    case 'REFERAT_DATA_NOT_FOUND':
      return 'Referat has not stored any meetings yet.'
    case 'INVALID_MEETING_ID':
      return 'This is not a Referat meeting id.'
    case 'MEETING_NOT_FOUND':
      return 'The meeting no longer exists in Referat.'
    case 'REFERAT_LAUNCH_FAILED':
      return 'Referat could not be started.'
    case 'INVALID_MEETING_FILE': {
      const { file, issues } = error as ReferatErrorLike
      const detail = Array.isArray(issues)
        ? issues
            .map((issue: { path?: string; message?: string }) =>
              issue.path ? `field "${issue.path}": ${issue.message}` : (issue.message ?? '')
            )
            .join('; ')
        : ''
      const name = typeof file === 'string' ? baseName(file) : 'A file'
      return `${name} could not be read${detail ? `: ${detail}` : ''}.`
    }
    default:
      return 'Referat’s data could not be read.'
  }
}

export function skippedRow(skipped: SkippedMeeting): SkippedRow {
  return { id: skipped.id, error: errorMessage(skipped.error) }
}

/** What the import window shows for one meeting and one of its summaries. */
export function meetingPreview(
  meeting: Meeting,
  summaryId: string | null,
  existing: ExistingRecord[],
  takenIds: ReadonlySet<string>
): MeetingPreview {
  const summary =
    (summaryId !== null ? findSummary(meeting, summaryId) : null) ??
    defaultSummary(meeting.summaries)
  if (summary === null) throw new Error('This meeting has no minutes to import.')
  const candidates = decisionCandidates(parseSummary(summary.markdown))
  const plan = buildImportPlan(meeting, {
    summaryId: summary.id,
    projectId: 'preview',
    folder: '',
    includeTranscript: false,
    decisions: candidates.map((candidate) => candidate.index),
    now: new Date()
  })
  return {
    id: meeting.id,
    title: noteTitle(meeting),
    held: formatMeetingTime(meeting.createdAt),
    duration: formatDuration(meeting.durationSec),
    summaries: meeting.summaries.map((s) => ({ id: s.id, label: summaryLabel(s) })),
    summaryId: summary.id,
    found: plan.found,
    decisions: candidates.map(({ index, title, markdown }) => ({ index, title, markdown })),
    transcriptSegments: meeting.transcript?.segments.length ?? 0,
    noteId: uniqueId(plan.note.baseId, takenIds),
    noteMarkdown: plan.note.body,
    existing
  }
}
