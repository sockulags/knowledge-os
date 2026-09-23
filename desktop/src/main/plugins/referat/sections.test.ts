import { describe, expect, it } from 'vitest'
import { demoteHeadings, parseSummary, sectionItems, sectionKind } from './sections'

const PROTOKOLL = `# Protokoll – Veckomöte

## Sammanfattning

Teamet gick igenom sprinten.

## Beslut

- Vi byter till Postgres för lagringen.
- Releasen flyttas till fredag.
  - Gäller bara webben.
- **Anna** äger kundkontakten.

## Actionpunkter

- [ ] Bengt: skriv migreringsplanen (fredag)

## Öppna frågor

1. Behöver vi en ny server?
`

describe('sectionKind', () => {
  it('recognises Swedish and English headings regardless of case, colon, and numbering', () => {
    expect(sectionKind('Beslut')).toBe('decisions')
    expect(sectionKind('3. Beslut:')).toBe('decisions')
    expect(sectionKind('**Decisions**')).toBe('decisions')
    expect(sectionKind('Action items')).toBe('actionItems')
    expect(sectionKind('ÖPPNA FRÅGOR')).toBe('openQuestions')
    expect(sectionKind('Open questions (2)')).toBe('openQuestions')
    expect(sectionKind('Summary')).toBe('summary')
    expect(sectionKind('Beslutsunderlag')).toBeNull()
  })
})

describe('parseSummary', () => {
  it('splits the protokoll template into its four sections and drops the title heading', () => {
    const parsed = parseSummary(PROTOKOLL)
    expect(parsed.sections.summary).toBe('Teamet gick igenom sprinten.')
    expect(parsed.sections.decisions).toContain('Postgres')
    expect(parsed.sections.actionItems).toBe('- [ ] Bengt: skriv migreringsplanen (fredag)')
    expect(parsed.sections.openQuestions).toBe('1. Behöver vi en ny server?')
    expect(parsed.preamble).toBe('')
    expect(parsed.other).toEqual([])
  })

  it('is heading level agnostic and reads English headings', () => {
    const parsed = parseSummary(
      '### Summary\nShort.\n#### Decisions\n- Ship it\n# Action items\n- Write docs\n'
    )
    expect(parsed.sections.summary).toBe('Short.')
    expect(parsed.sections.decisions).toBe('- Ship it')
    expect(parsed.sections.actionItems).toBe('- Write docs')
  })

  it('keeps sub-headings inside a recognised section and stops at the next known heading', () => {
    const parsed = parseSummary(
      '## Beslut\n### Budget\nÖkas.\n### Personal\nOförändrad.\n### Öppna frågor\n- Vem?\n'
    )
    expect(parsed.sections.decisions).toBe('### Budget\nÖkas.\n### Personal\nOförändrad.')
    expect(parsed.sections.openQuestions).toBe('- Vem?')
  })

  it('treats a bold line with a known name as a heading', () => {
    const parsed = parseSummary(
      'Intro text.\n\n**Beslut:**\n- Ja\n\n**Viktigt**\nInte en rubrik.\n'
    )
    expect(parsed.preamble).toBe('Intro text.')
    expect(parsed.sections.decisions).toBe('- Ja\n\n**Viktigt**\nInte en rubrik.')
  })

  it('reports missing sections as absent and keeps unknown sections', () => {
    const parsed = parseSummary('## Deltagare\nAnna, Bengt\n\n## Sammanfattning\nKort möte.\n')
    expect(parsed.sections.decisions).toBeUndefined()
    expect(parsed.sections.actionItems).toBeUndefined()
    expect(parsed.other).toEqual([{ heading: 'Deltagare', content: 'Anna, Bengt' }])
  })

  it('ignores headings inside fenced code', () => {
    const parsed = parseSummary('## Sammanfattning\n```\n## Beslut\n```\n')
    expect(parsed.sections.decisions).toBeUndefined()
    expect(parsed.sections.summary).toBe('```\n## Beslut\n```')
  })

  it('joins two sections of the same kind', () => {
    const parsed = parseSummary('## Beslut\n- A\n## Övrigt\nx\n## Decisions\n- B\n')
    expect(sectionItems(parsed.sections.decisions ?? '').map((item) => item.text)).toEqual([
      'A',
      'B'
    ])
  })
})

describe('sectionItems', () => {
  it('takes top-level list items and folds nested items into their detail', () => {
    const items = sectionItems(parseSummary(PROTOKOLL).sections.decisions ?? '')
    expect(items).toEqual([
      { text: 'Vi byter till Postgres för lagringen.', detail: '' },
      { text: 'Releasen flyttas till fredag.', detail: '- Gäller bara webben.' },
      { text: '**Anna** äger kundkontakten.', detail: '' }
    ])
  })

  it('handles ordered lists, indented lists, and task boxes', () => {
    expect(sectionItems('  1) Första\n  2) Andra\n     fortsättning').map((i) => i.text)).toEqual([
      'Första',
      'Andra'
    ])
    expect(sectionItems('- [x] Klart')[0].text).toBe('Klart')
  })

  it('falls back to sub-headings, then paragraphs', () => {
    expect(sectionItems('### Budget\nÖkas.\n### Personal\n').map((i) => i.text)).toEqual([
      'Budget',
      'Personal'
    ])
    expect(sectionItems('Vi väljer A.\n\nVi väljer B.').map((i) => i.text)).toEqual([
      'Vi väljer A.',
      'Vi väljer B.'
    ])
  })

  it('reads placeholders as no items', () => {
    expect(sectionItems('Inga beslut fattades.')).toEqual([])
    expect(sectionItems('- Inga')).toEqual([])
    expect(sectionItems('_No decisions were made._')).toEqual([])
    expect(sectionItems('None.')).toEqual([])
    expect(sectionItems('')).toEqual([])
  })
})

describe('demoteHeadings', () => {
  it('pushes shallow headings down but leaves code and deeper headings alone', () => {
    expect(demoteHeadings('# A\n#### B\n```\n# C\n```\nx # y', 3)).toBe(
      '### A\n#### B\n```\n# C\n```\nx # y'
    )
  })
})
