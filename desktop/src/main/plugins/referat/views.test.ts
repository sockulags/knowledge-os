import { describe, expect, it } from 'vitest'
import { InvalidMeetingFileError, ReferatNotInstalledError } from 'referat-sdk'
import { meeting } from './fixtures'
import { errorMessage, meetingPreview, meetingRow } from './views'

describe('meetingRow', () => {
  it('shows an in-progress meeting but does not offer it for import', () => {
    const row = meetingRow({ ...meeting(), status: 'transcribing', inProgress: true })
    expect(row.importable).toBe(false)
    expect(row.status).toBe('Transcribing')
    expect(row.reason).toContain('still working')
  })

  it('offers a finished meeting with minutes', () => {
    const row = meetingRow(meeting())
    expect(row).toMatchObject({ importable: true, reason: null, duration: '47 min' })
    expect(JSON.stringify(row)).not.toContain('/synthetic')
  })
})

describe('errorMessage', () => {
  it('names a broken file by its base name only', () => {
    const error = new InvalidMeetingFileError('C:\\Users\\x\\referat\\meetings\\m\\meta.json', [
      { path: 'title', message: 'Required' }
    ])
    const message = errorMessage(error)
    expect(message).toBe('meta.json could not be read: field "title": Required.')
    expect(message).not.toContain('Users')
    expect(errorMessage(new ReferatNotInstalledError(['C:\\a\\referat.exe']))).toBe(
      'Referat is not installed.'
    )
  })
})

describe('meetingPreview', () => {
  it('lists decisions, the proposed note id, and no file paths', () => {
    const preview = meetingPreview(meeting(), null, [], new Set())
    expect(preview.decisions.map((d) => d.index)).toEqual([0, 1, 2])
    expect(preview.transcriptSegments).toBe(2)
    expect(preview.noteMarkdown).not.toContain('## Transcript')
    expect(JSON.stringify(preview)).not.toContain('/synthetic')
    const taken = meetingPreview(meeting(), null, [], new Set([preview.noteId]))
    expect(taken.noteId).toBe(`${preview.noteId}-2`)
  })
})
