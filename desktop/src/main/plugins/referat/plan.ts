// Turns one Referat meeting into the records an import creates: one active
// note and one draft decision per item under the decisions heading. Pure:
// ids are resolved and records written later, by the importer.

import { createHash } from 'crypto'
import type { Meeting, MeetingSummary } from 'referat-sdk'
import { decisionBaseId, localDate, noteBaseId } from './ids'
import {
  demoteHeadings,
  parseSummary,
  plainText,
  sectionItems,
  type ParsedSummary,
  type SectionKind
} from './sections'

export const PROVENANCE_KIND = 'referat-meeting'
export const DEFAULT_TEMPLATE_ID = 'protokoll'
export const DEFAULT_FOLDER = 'meeting-notes'
const TITLE_MAX_LENGTH = 120

export function provenanceReference(meetingId: string): string {
  return `referat:${meetingId}`
}

const MONTHS = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December'
]

/** "20 September 2026, 14:03" on this computer's clock. */
export function formatMeetingTime(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  const time = `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
  return `${date.getDate()} ${MONTHS[date.getMonth()]} ${date.getFullYear()}, ${time}`
}

/** "47 min", "1 h 5 min", "under a minute". */
export function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 60) return 'under a minute'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes} min`
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  return rest === 0 ? `${hours} h` : `${hours} h ${rest} min`
}

function formatOffset(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds))
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  const mm = String(m).padStart(2, '0')
  const ss = String(s).padStart(2, '0')
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`
}

/** A short label for a summary in a picker: its template name and focus. */
export function summaryLabel(summary: MeetingSummary): string {
  return summary.focus ? `${summary.templateName} (focus: ${summary.focus})` : summary.templateName
}

/**
 * The summary imported when the user picks none: the newest "protokoll"
 * summary without a focus, else the newest "protokoll", else the newest.
 * Referat lists summaries oldest first.
 */
export function defaultSummary(summaries: readonly MeetingSummary[]): MeetingSummary | null {
  const newestFirst = [...summaries].reverse()
  return (
    newestFirst.find((s) => s.templateId === DEFAULT_TEMPLATE_ID && s.focus === '') ??
    newestFirst.find((s) => s.templateId === DEFAULT_TEMPLATE_ID) ??
    newestFirst[0] ??
    null
  )
}

function truncateTitle(text: string): string {
  const plain = plainText(text).replace(/[.:;]+$/, '')
  if (plain.length <= TITLE_MAX_LENGTH) return plain
  const cut = plain.slice(0, TITLE_MAX_LENGTH)
  const boundary = cut.lastIndexOf(' ')
  return `${(boundary > 40 ? cut.slice(0, boundary) : cut).replace(/[\s,.;:]+$/, '')}…`
}

export interface DecisionCandidate {
  /** Position under the decisions heading; the user ticks decisions by this index. */
  index: number
  title: string
  /** The decision as written in the minutes, with anything nested under it. */
  markdown: string
}

export function decisionCandidates(parsed: ParsedSummary): DecisionCandidate[] {
  const content = parsed.sections.decisions
  if (content === undefined) return []
  return sectionItems(content).map((item, index) => ({
    index,
    title: truncateTitle(item.text) || `Decision ${index + 1}`,
    markdown: item.detail === '' ? item.text : `${item.text}\n\n${item.detail}`
  }))
}

export interface ProvenanceEntry {
  kind: string
  reference: string
  captured: string
  sha256: string
}

/** One record to create. `id` and `related` are filled in by the importer. */
export interface PlannedRecord {
  kind: 'note' | 'decision'
  baseId: string
  title: string
  /** Frontmatter without `id`; decisions get `related: [note id]` when written. */
  metadata: Record<string, unknown>
  body: string
}

export interface ImportPlan {
  meetingId: string
  reference: string
  projectId: string
  folder: string
  note: PlannedRecord
  decisions: PlannedRecord[]
  /** What the minutes contained, for the preview and the result message. */
  found: Record<SectionKind, boolean>
}

export interface PlanOptions {
  summaryId: string
  projectId: string
  /** Folder inside the project, '' for the project's top level. */
  folder: string
  includeTranscript: boolean
  /** Indexes of the decision candidates the user kept ticked. */
  decisions: readonly number[]
  /** The import time, for provenance. */
  now: Date
}

function transcriptMarkdown(meeting: Meeting): string {
  const transcript = meeting.transcript
  if (transcript === null || transcript.segments.length === 0) return ''
  // Only segment text and speaker display names are used; voice embeddings
  // are never requested from the SDK and never read here.
  return transcript.segments
    .map((segment) => {
      const speaker = segment.speaker
        ? (transcript.speakers?.[segment.speaker] ?? segment.speaker)
        : ''
      const label = speaker
        ? `[${formatOffset(segment.startSec)}] ${speaker}:`
        : `[${formatOffset(segment.startSec)}]`
      return `**${label}** ${segment.text.replace(/\s+/g, ' ').trim()}`
    })
    .join('\n\n')
}

const SECTION_TITLES: Record<SectionKind, string> = {
  summary: 'Summary',
  decisions: 'Decisions',
  actionItems: 'Action items',
  openQuestions: 'Open questions'
}

/** The line under the note's decisions saying which ones became draft decision records. */
function draftsSentence(imported: number, listed: number): string {
  if (imported === 0) return ''
  const which =
    imported === listed
      ? listed === 1
        ? 'This decision was imported as a draft decision'
        : 'These decisions were imported as draft decisions'
      : imported === 1
        ? `One of these ${listed} decisions was imported as a draft decision`
        : `${imported} of these ${listed} decisions were imported as draft decisions`
  return `\n\n${which} linked to this note. Drafts govern nothing until someone accepts them.`
}

function noteBody(
  meeting: Meeting,
  summary: MeetingSummary,
  parsed: ParsedSummary,
  includeTranscript: boolean,
  imported: number,
  listed: number
): string {
  const parts: string[] = [
    [
      `- **Held:** ${formatMeetingTime(meeting.createdAt)}`,
      `- **Duration:** ${formatDuration(meeting.durationSec)}`,
      `- **Minutes:** ${summaryLabel(summary)}, written by Referat`,
      `- **Referat meeting:** \`${provenanceReference(meeting.id)}\``
    ].join('\n')
  ]
  const section = (title: string, content: string): void => {
    if (content.trim() !== '') parts.push(`## ${title}\n\n${demoteHeadings(content, 3)}`)
  }
  const { sections, preamble, other } = parsed
  if (sections.summary !== undefined) {
    if (preamble !== '') parts.push(demoteHeadings(preamble, 3))
    section(SECTION_TITLES.summary, sections.summary)
  } else {
    section(SECTION_TITLES.summary, preamble)
  }
  if (sections.decisions !== undefined) {
    section(SECTION_TITLES.decisions, `${sections.decisions}${draftsSentence(imported, listed)}`)
  }
  section(SECTION_TITLES.actionItems, sections.actionItems ?? '')
  section(SECTION_TITLES.openQuestions, sections.openQuestions ?? '')
  for (const item of other) section(plainText(item.heading) || 'Notes', item.content)
  if (includeTranscript) section('Transcript', transcriptMarkdown(meeting))
  return `${parts.join('\n\n')}\n`
}

function decisionBody(meeting: Meeting, candidate: DecisionCandidate): string {
  const title = meeting.title.trim() || 'a meeting'
  return [
    `## Decision\n\n${demoteHeadings(candidate.markdown, 3)}`,
    `## Context\n\nRecorded under the decisions in the minutes of the meeting "${plainText(title)}" on ${formatMeetingTime(meeting.createdAt)}, recorded with Referat (\`${provenanceReference(meeting.id)}\`). The meeting note is linked under related records.`,
    'Imported as a draft: this decision governs nothing until someone accepts it.'
  ].join('\n\n')
}

export function findSummary(meeting: Meeting, summaryId: string): MeetingSummary | null {
  return meeting.summaries.find((summary) => summary.id === summaryId) ?? null
}

export function noteTitle(meeting: Meeting): string {
  return meeting.title.trim() || `Meeting on ${formatMeetingTime(meeting.createdAt)}`
}

export function noteBaseIdFor(meeting: Meeting): string {
  return noteBaseId(localDate(meeting.createdAt), noteTitle(meeting))
}

/** The records one import creates, before ids are resolved against the knowledge base. */
export function buildImportPlan(meeting: Meeting, options: PlanOptions): ImportPlan {
  const summary = findSummary(meeting, options.summaryId)
  if (summary === null) throw new Error('The chosen summary no longer exists in this meeting.')
  const parsed = parseSummary(summary.markdown)
  const candidates = decisionCandidates(parsed)
  const chosen = candidates.filter((candidate) => options.decisions.includes(candidate.index))

  const reference = provenanceReference(meeting.id)
  const provenance: ProvenanceEntry[] = [
    {
      kind: PROVENANCE_KIND,
      reference,
      captured: options.now.toISOString().replace(/\.\d{3}Z$/, 'Z'),
      sha256: createHash('sha256').update(summary.markdown, 'utf8').digest('hex')
    }
  ]
  const scope = `project:${options.projectId}`
  const date = localDate(meeting.createdAt)
  const title = noteTitle(meeting)

  const note: PlannedRecord = {
    kind: 'note',
    baseId: noteBaseId(date, title),
    title,
    metadata: { title, type: 'project', status: 'active', scope, provenance },
    body: noteBody(
      meeting,
      summary,
      parsed,
      options.includeTranscript,
      chosen.length,
      candidates.length
    )
  }
  const decisions: PlannedRecord[] = chosen.map((candidate) => ({
    kind: 'decision',
    baseId: decisionBaseId(date, candidate.title),
    title: candidate.title,
    metadata: {
      title: candidate.title,
      type: 'project',
      record_kind: 'decision',
      // The approval policy: imported decisions are proposals only.
      status: 'draft',
      scope,
      provenance
    },
    body: `${decisionBody(meeting, candidate)}\n`
  }))

  return {
    meetingId: meeting.id,
    reference,
    projectId: options.projectId,
    folder: options.folder,
    note,
    decisions,
    found: {
      summary: parsed.sections.summary !== undefined,
      decisions: parsed.sections.decisions !== undefined,
      actionItems: parsed.sections.actionItems !== undefined,
      openQuestions: parsed.sections.openQuestions !== undefined
    }
  }
}
