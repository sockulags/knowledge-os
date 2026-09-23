import { describe, expect, it } from 'vitest'
import {
  cleanFolder,
  decisionBaseId,
  isSuffixedForm,
  localDate,
  noteBaseId,
  RECORD_ID_PATTERN,
  slugify,
  uniqueId
} from './ids'

describe('slugify', () => {
  it('turns Swedish and other letters into readable ASCII words', () => {
    expect(slugify('Veckomöte för Åre-gänget')).toBe('veckomote-for-are-ganget')
    expect(slugify('Straße & Smørrebrød')).toBe('strasse-smorrebrod')
    expect(slugify('  **Vi** byter till `Postgres`!  ')).toBe('vi-byter-till-postgres')
    expect(slugify('日本語')).toBe('')
  })

  it('cuts long text at a word boundary', () => {
    const slug = slugify('Releasen flyttas till fredag eftersom testerna inte hann bli klara', 30)
    expect(slug).toBe('releasen-flyttas-till-fredag')
    expect(slug.length).toBeLessThanOrEqual(30)
    expect(slugify('a'.repeat(80), 20)).toBe('a'.repeat(20))
  })
})

describe('record ids', () => {
  it('derives ids from the date and the title or decision text', () => {
    expect(noteBaseId('2026-09-20', 'Veckomöte')).toBe('2026-09-20-veckomote')
    expect(noteBaseId('2026-09-20', '???')).toBe('2026-09-20-meeting')
    expect(decisionBaseId('2026-09-20', 'Vi byter till Postgres.')).toBe(
      '2026-09-20-vi-byter-till-postgres'
    )
    expect(decisionBaseId('2026-09-20', '')).toBe('2026-09-20-decision')
    for (const id of ['2026-09-20-veckomote', '2026-09-20-decision']) {
      expect(RECORD_ID_PATTERN.test(id)).toBe(true)
    }
  })

  it('uses the local calendar date of the meeting', () => {
    const noon = new Date(2026, 8, 20, 12, 0, 0)
    expect(localDate(noon.toISOString())).toBe('2026-09-20')
  })

  it('suffixes an id that is taken instead of reusing it', () => {
    expect(uniqueId('a-b', new Set())).toBe('a-b')
    expect(uniqueId('a-b', new Set(['a-b']))).toBe('a-b-2')
    expect(uniqueId('a-b', new Set(['a-b', 'a-b-2', 'a-b-3']))).toBe('a-b-4')
  })

  it('recognises suffixed forms of a base id', () => {
    expect(isSuffixedForm('a-b', 'a-b')).toBe(true)
    expect(isSuffixedForm('a-b-12', 'a-b')).toBe(true)
    expect(isSuffixedForm('a-b-c', 'a-b')).toBe(false)
    expect(isSuffixedForm('a-bc', 'a-b')).toBe(false)
  })
})

describe('cleanFolder', () => {
  it('accepts relative folders and normalises separators', () => {
    expect(cleanFolder('meeting-notes')).toBe('meeting-notes')
    expect(cleanFolder(' /meetings\\2026/ ')).toBe('meetings/2026')
    expect(cleanFolder('')).toBe('')
  })

  it('refuses paths that could leave the project', () => {
    expect(cleanFolder('../other')).toBeNull()
    expect(cleanFolder('notes/..')).toBeNull()
    expect(cleanFolder('C:/x')).toBeNull()
    expect(cleanFolder('.hidden')).toBeNull()
  })
})
