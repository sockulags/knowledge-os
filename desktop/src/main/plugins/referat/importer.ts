// Writes an import plan through the local write API and reports exactly what
// was created, and finds an earlier import of the same meeting. Talks to the
// knowledge base only through the `KosApi` interface (see kosClient.ts),
// never through the file system.

import { isSuffixedForm, uniqueId } from './ids'
import { PROVENANCE_KIND, type ImportPlan, type PlannedRecord } from './plan'

export interface CommitInfo {
  committed: boolean
  sha?: string | null
  skipped?: string | null
}

export type CreateOutcome =
  | { ok: true; id: string; commit: CommitInfo | null }
  | { ok: false; status: number; error: string; detail: string }

export interface RecordInfo {
  id: string
  title: string
  isDecision: boolean
  provenance: { kind: string; reference: string }[]
}

/** The parts of the local API the plugin uses. */
export interface KosApi {
  /** Every record id in the knowledge base. */
  recordIds(): Promise<string[]>
  /** Record ids whose text matches `query`; empty when search is unavailable. */
  search(query: string): Promise<string[]>
  /** One record, or null when it does not exist. */
  record(id: string): Promise<RecordInfo | null>
  /** `POST /api/records`. */
  createRecord(payload: {
    metadata: Record<string, unknown>
    body: string
    project_path?: string
  }): Promise<CreateOutcome>
}

export interface CreatedRecord {
  kind: 'note' | 'decision'
  id: string
  title: string
  commit: CommitInfo | null
}

export interface FailedRecord {
  kind: 'note' | 'decision'
  title: string
  error: string
  detail: string
}

export interface ImportResult {
  noteId: string | null
  created: CreatedRecord[]
  failed: FailedRecord[]
  /** Decisions not tried because the note could not be created. */
  notAttempted: FailedRecord[]
  /** Planned records still to write: the failed decisions, for a retry. */
  pending: PlannedRecord[]
}

/** Retries per record after a `duplicate` answer, each time with the next free suffix. */
const MAX_DUPLICATE_RETRIES = 20

function projectPath(folder: string, id: string): string | undefined {
  return folder === '' ? undefined : `${folder}/${id}.md`
}

async function createOne(
  api: KosApi,
  record: PlannedRecord,
  folder: string,
  taken: Set<string>,
  extra: Record<string, unknown>
): Promise<{ ok: true; id: string; commit: CommitInfo | null } | FailedRecord> {
  let last: CreateOutcome | null = null
  for (let attempt = 0; attempt <= MAX_DUPLICATE_RETRIES; attempt++) {
    const id = uniqueId(record.baseId, taken)
    const outcome = await api.createRecord({
      metadata: { id, ...record.metadata, ...extra },
      body: record.body,
      project_path: projectPath(folder, id)
    })
    taken.add(id)
    if (outcome.ok) return { ok: true, id: outcome.id, commit: outcome.commit }
    last = outcome
    // Someone else took the id or the file name since the ids were read:
    // move on to the next suffix, never overwrite.
    if (outcome.error !== 'duplicate') break
  }
  return {
    kind: record.kind,
    title: record.title,
    error: last?.ok === false ? last.error : 'unknown',
    detail: last?.ok === false ? last.detail : 'The record was not created.'
  }
}

/**
 * Creates the note first, then each decision linked to it. When the note
 * fails nothing else is written, so a decision never points at a missing
 * note. `existingNoteId` retries decisions for a note created earlier.
 */
export async function executePlan(
  api: KosApi,
  plan: Pick<ImportPlan, 'folder' | 'note' | 'decisions'>,
  existingNoteId: string | null = null
): Promise<ImportResult> {
  const taken = new Set(await api.recordIds())
  const result: ImportResult = {
    noteId: existingNoteId,
    created: [],
    failed: [],
    notAttempted: [],
    pending: []
  }

  if (existingNoteId === null) {
    const note = await createOne(api, plan.note, plan.folder, taken, {})
    if (!('ok' in note)) {
      result.failed.push(note)
      result.notAttempted = plan.decisions.map((decision) => ({
        kind: 'decision',
        title: decision.title,
        error: 'not_attempted',
        detail: 'Not created because the meeting note could not be created.'
      }))
      return result
    }
    result.noteId = note.id
    result.created.push({ kind: 'note', id: note.id, title: plan.note.title, commit: note.commit })
  }

  for (const decision of plan.decisions) {
    const outcome = await createOne(api, decision, plan.folder, taken, {
      related: [result.noteId]
    })
    if ('ok' in outcome) {
      result.created.push({
        kind: 'decision',
        id: outcome.id,
        title: decision.title,
        commit: outcome.commit
      })
    } else {
      result.failed.push(outcome)
      result.pending.push(decision)
    }
  }
  return result
}

export interface ExistingImport {
  id: string
  title: string
  isDecision: boolean
}

/**
 * Records that already carry this meeting's provenance. Candidates come from
 * a text search for the meeting id (the note body names it) and from ids of
 * the note's base id or a suffixed form; each one is confirmed by reading its
 * provenance, so a search hit alone never counts.
 */
export async function findExistingImport(
  api: KosApi,
  meetingId: string,
  noteBaseId: string
): Promise<ExistingImport[]> {
  const reference = `referat:${meetingId}`
  const [hits, ids] = await Promise.all([api.search(meetingId), api.recordIds()])
  const candidates = new Set([...hits, ...ids.filter((id) => isSuffixedForm(id, noteBaseId))])
  const found: ExistingImport[] = []
  for (const id of candidates) {
    const record = await api.record(id)
    if (record === null) continue
    const matches = record.provenance.some(
      (entry) => entry.kind === PROVENANCE_KIND && entry.reference === reference
    )
    if (matches) found.push({ id: record.id, title: record.title, isDecision: record.isDecision })
  }
  // The note first, then its decisions, each group by id.
  return found.sort(
    (a, b) => Number(a.isDecision) - Number(b.isDecision) || a.id.localeCompare(b.id)
  )
}
