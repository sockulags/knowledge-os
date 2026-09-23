import { createHash } from 'crypto'
import { describe, expect, it } from 'vitest'
import { localDate } from './ids'
import { meeting, PROTOKOLL_MARKDOWN, summary } from './fixtures'
import { buildImportPlan, defaultSummary, formatDuration, type PlanOptions } from './plan'

const NOW = new Date('2026-09-23T08:30:00.123Z')
const DATE = localDate('2026-09-20T12:00:00.000Z')

function options(overrides: Partial<PlanOptions> = {}): PlanOptions {
  return {
    summaryId: 'sum-1',
    projectId: 'demo',
    folder: 'meeting-notes',
    includeTranscript: false,
    decisions: [0, 1, 2],
    now: NOW,
    ...overrides
  }
}

describe('buildImportPlan', () => {
  it('maps a finished protokoll meeting to one active note and draft decisions', () => {
    const plan = buildImportPlan(meeting(), options({ decisions: [0, 2] }))

    expect(plan.reference).toBe('referat:20260920120000-abc123')
    expect(plan.found).toEqual({
      summary: true,
      decisions: true,
      actionItems: true,
      openQuestions: true
    })

    const provenance = [
      {
        kind: 'referat-meeting',
        reference: 'referat:20260920120000-abc123',
        captured: '2026-09-23T08:30:00Z',
        sha256: createHash('sha256').update(PROTOKOLL_MARKDOWN, 'utf8').digest('hex')
      }
    ]
    expect(plan.note.baseId).toBe(`${DATE}-planeringsmote`)
    expect(plan.note.metadata).toEqual({
      title: 'Planeringsmöte',
      type: 'project',
      status: 'active',
      scope: 'project:demo',
      provenance
    })
    const body = plan.note.body
    expect(body).toContain('- **Duration:** 47 min')
    expect(body).toContain('`referat:20260920120000-abc123`')
    expect(body).toContain('## Summary\n\nTeamet planerade nästa kvartal.')
    expect(body).toContain('## Action items\n\n- Bengt skriver migreringsplanen.')
    expect(body).toContain('## Open questions\n\n- Behöver vi en ny server?')
    expect(body).toContain('2 of these decisions were imported as a draft decision')
    expect(body).not.toContain('## Transcript')
    expect(body).not.toContain('# Protokoll')

    expect(plan.decisions.map((d) => d.title)).toEqual([
      'Vi byter till Postgres för lagringen',
      'Kundmötet hålls på plats'
    ])
    expect(plan.decisions[0].baseId).toBe(`${DATE}-vi-byter-till-postgres-for-lagringen`)
    expect(plan.decisions[0].metadata).toEqual({
      title: 'Vi byter till Postgres för lagringen',
      type: 'project',
      record_kind: 'decision',
      status: 'draft',
      scope: 'project:demo',
      provenance
    })
    expect(plan.decisions[0].body).toContain('## Decision\n\nVi byter till Postgres för lagringen.')
    expect(plan.decisions[0].body).toContain('referat:20260920120000-abc123')
  })

  it('keeps nested lines with their decision', () => {
    const plan = buildImportPlan(meeting(), options({ decisions: [1] }))
    expect(plan.decisions[0].body).toContain(
      'Releasen flyttas till fredag.\n\n- Gäller bara webbversionen.'
    )
  })

  it('imports no decisions when the minutes have no decisions heading', () => {
    const plain = summary({ markdown: '## Sammanfattning\nKort.\n\n## Actionpunkter\n- Gör X\n' })
    const plan = buildImportPlan(meeting({ summaries: [plain] }), options())
    expect(plan.found.decisions).toBe(false)
    expect(plan.decisions).toEqual([])
    expect(plan.note.body).not.toContain('## Decisions')
  })

  it('adds the full transcript only when asked, with speaker names', () => {
    const plan = buildImportPlan(meeting(), options({ includeTranscript: true }))
    expect(plan.note.body).toContain('## Transcript\n\n**[00:00] Anna:** Hej allihop.')
    expect(plan.note.body).toContain('**[01:05] S2:** Vi börjar.')
  })

  it('refuses a summary that is not in the meeting', () => {
    expect(() => buildImportPlan(meeting(), options({ summaryId: 'gone' }))).toThrow()
  })
})

describe('defaultSummary', () => {
  it('prefers the newest protokoll without a focus', () => {
    const summaries = [
      summary({ id: 'old', templateId: 'protokoll' }),
      summary({ id: 'focus', templateId: 'protokoll', focus: 'budget' }),
      summary({ id: 'other', templateId: 'sammandrag', templateName: 'Sammandrag' })
    ]
    expect(defaultSummary(summaries)?.id).toBe('old')
    expect(defaultSummary([summaries[2]])?.id).toBe('other')
    expect(defaultSummary([])).toBeNull()
  })
})

describe('formatDuration', () => {
  it('reads as minutes and hours', () => {
    expect(formatDuration(20)).toBe('under a minute')
    expect(formatDuration(47 * 60)).toBe('47 min')
    expect(formatDuration(65 * 60)).toBe('1 h 5 min')
    expect(formatDuration(120 * 60)).toBe('2 h')
  })
})
