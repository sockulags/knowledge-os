import { describe, expect, it } from 'vitest'
import { meeting } from './fixtures'
import {
  executePlan,
  findExistingImport,
  type CreateOutcome,
  type KosApi,
  type RecordInfo
} from './importer'
import { buildImportPlan } from './plan'

type Payload = Parameters<KosApi['createRecord']>[0]

/** An in-memory stand-in for the local API. */
class FakeKos implements KosApi {
  records = new Map<string, RecordInfo>()
  posts: Payload[] = []
  searchable = true
  /** Ids that answer `duplicate` although recordIds() does not list them (a race). */
  hidden = new Set<string>()
  /** Titles whose create is refused. */
  refuse = new Set<string>()

  async recordIds(): Promise<string[]> {
    return [...this.records.keys()]
  }

  async search(query: string): Promise<string[]> {
    if (!this.searchable) return []
    return [...this.records.values()]
      .filter((record) => record.provenance.some((entry) => entry.reference.endsWith(query)))
      .map((record) => record.id)
  }

  async record(id: string): Promise<RecordInfo | null> {
    return this.records.get(id) ?? null
  }

  async createRecord(payload: Payload): Promise<CreateOutcome> {
    this.posts.push(payload)
    const id = payload.metadata['id'] as string
    const title = payload.metadata['title'] as string
    if (this.records.has(id) || this.hidden.has(id)) {
      return { ok: false, status: 409, error: 'duplicate', detail: `${id} already exists` }
    }
    if (this.refuse.has(title)) {
      return { ok: false, status: 422, error: 'validation', detail: 'refused by the core' }
    }
    this.records.set(id, {
      id,
      title,
      isDecision: payload.metadata['record_kind'] === 'decision',
      provenance: payload.metadata['provenance'] as RecordInfo['provenance']
    })
    return { ok: true, id, commit: { committed: true, sha: 'abcdef1234567' } }
  }
}

function plan(decisions = [0, 1, 2]): ReturnType<typeof buildImportPlan> {
  return buildImportPlan(meeting(), {
    summaryId: 'sum-1',
    projectId: 'demo',
    folder: 'meeting-notes',
    includeTranscript: false,
    decisions,
    now: new Date('2026-09-23T08:30:00Z')
  })
}

describe('executePlan', () => {
  it('creates the note first, then decisions related to it, in the chosen folder', async () => {
    const kos = new FakeKos()
    const p = plan([0, 2])
    const result = await executePlan(kos, p)

    expect(result.failed).toEqual([])
    expect(result.created.map((r) => r.kind)).toEqual(['note', 'decision', 'decision'])
    const noteId = p.note.baseId
    expect(result.noteId).toBe(noteId)
    expect(kos.posts[0].project_path).toBe(`meeting-notes/${noteId}.md`)
    for (const post of kos.posts.slice(1)) {
      expect(post.metadata['related']).toEqual([noteId])
      expect(post.metadata['status']).toBe('draft')
    }
  })

  it('suffixes ids that already exist and never overwrites', async () => {
    const kos = new FakeKos()
    const p = plan([0])
    const existing = { id: p.note.baseId, title: 'Other', isDecision: false, provenance: [] }
    kos.records.set(existing.id, existing)
    kos.hidden.add(`${p.decisions[0].baseId}`)

    const result = await executePlan(kos, p)

    expect(result.created.map((r) => r.id)).toEqual([
      `${p.note.baseId}-2`,
      `${p.decisions[0].baseId}-2`
    ])
    expect(kos.records.get(p.note.baseId)).toBe(existing)
    // The decision's first attempt answered duplicate and was retried with a suffix.
    expect(kos.posts.map((post) => post.metadata['id'])).toEqual([
      `${p.note.baseId}-2`,
      p.decisions[0].baseId,
      `${p.decisions[0].baseId}-2`
    ])
  })

  it('gives two identical decisions distinct ids', async () => {
    const kos = new FakeKos()
    const p = plan([0])
    const result = await executePlan(kos, { ...p, decisions: [p.decisions[0], p.decisions[0]] })
    const ids = result.created.filter((r) => r.kind === 'decision').map((r) => r.id)
    expect(new Set(ids).size).toBe(2)
  })

  it('writes nothing else when the note fails', async () => {
    const kos = new FakeKos()
    const p = plan()
    kos.refuse.add(p.note.title)
    const result = await executePlan(kos, p)
    expect(result.created).toEqual([])
    expect(result.failed).toEqual([
      { kind: 'note', title: p.note.title, error: 'validation', detail: 'refused by the core' }
    ])
    expect(result.notAttempted).toHaveLength(3)
    expect(kos.posts).toHaveLength(1)
  })

  it('reports a partial import exactly and can retry the failed decisions', async () => {
    const kos = new FakeKos()
    const p = plan()
    kos.refuse.add(p.decisions[1].title)
    const first = await executePlan(kos, p)
    expect(first.created.map((r) => r.title)).toEqual([
      p.note.title,
      p.decisions[0].title,
      p.decisions[2].title
    ])
    expect(first.failed.map((r) => r.title)).toEqual([p.decisions[1].title])
    expect(first.pending).toEqual([p.decisions[1]])

    kos.refuse.clear()
    const retry = await executePlan(kos, { ...p, decisions: first.pending }, first.noteId)
    expect(retry.created).toHaveLength(1)
    expect(retry.created[0].kind).toBe('decision')
    expect(kos.posts.at(-1)?.metadata['related']).toEqual([first.noteId])
  })
})

describe('findExistingImport', () => {
  it('finds an earlier import of the same meeting by its provenance', async () => {
    const kos = new FakeKos()
    const p = plan([0])
    await executePlan(kos, p)
    const found = await findExistingImport(kos, '20260920120000-abc123', p.note.baseId)
    expect(found.map((r) => r.isDecision)).toEqual([false, true])
    expect(found[0].id).toBe(p.note.baseId)
  })

  it('still finds the note by id when search is unavailable', async () => {
    const kos = new FakeKos()
    const p = plan([])
    kos.records.set(p.note.baseId, {
      id: p.note.baseId,
      title: 'Taken',
      isDecision: false,
      provenance: []
    })
    await executePlan(kos, p)
    kos.searchable = false
    const found = await findExistingImport(kos, '20260920120000-abc123', p.note.baseId)
    expect(found.map((r) => r.id)).toEqual([`${p.note.baseId}-2`])
  })

  it('ignores records of another meeting or without that provenance', async () => {
    const kos = new FakeKos()
    kos.records.set('x', {
      id: 'x',
      title: 'X',
      isDecision: false,
      provenance: [{ kind: 'referat-meeting', reference: 'referat:20260101000000-other' }]
    })
    const found = await findExistingImport(kos, '20260920120000-abc123', 'x')
    expect(found).toEqual([])
  })
})
