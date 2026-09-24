import { describe, expect, it } from 'vitest'
import { folderNameFromUrl, folderNameProblem, gitUrlProblem } from './clone'

describe('folderNameFromUrl', () => {
  it.each([
    ['https://github.com/you/notes.git', 'notes'],
    ['https://github.com/you/notes', 'notes'],
    ['https://github.com/you/notes.git/', 'notes'],
    ['git@github.com:you/team-notes.git', 'team-notes'],
    ['git@host:notes.git', 'notes'],
    ['ssh://git@example.com:2222/you/Work%20Notes.git', 'Work Notes'],
    ['C:\\repos\\kb.git', 'kb'],
    ['D:/repos/kb', 'kb'],
    ['file:///C:/repos/shared.git', 'shared'],
    ['https://example.com/you/notes.git?ref=main#top', 'notes'],
    ['  https://example.com/a/b.GIT  ', 'b']
  ])('%s -> %s', (url, name) => {
    expect(folderNameFromUrl(url)).toBe(name)
  })

  it('leaves the name empty when nothing usable remains', () => {
    expect(folderNameFromUrl('')).toBe('')
    expect(folderNameFromUrl('https://example.com/')).toBe('example.com')
    expect(folderNameFromUrl('https://example.com/.git')).toBe('')
    expect(folderNameFromUrl('https://example.com/con.git')).toBe('')
  })

  it('replaces characters Windows does not allow', () => {
    expect(folderNameFromUrl('https://example.com/a%3Ab.git')).toBe('a-b')
  })
})

describe('gitUrlProblem', () => {
  it.each([
    'https://github.com/you/notes.git',
    'http://127.0.0.1:8080/kb.git',
    'ssh://git@example.com:2222/you/notes.git',
    'git@github.com:you/notes.git',
    'file:///C:/repos/notes.git',
    'C:\\repos\\notes.git',
    '\\\\server\\share\\notes.git',
    '/srv/git/notes.git',
    'https://you@github.com/you/notes.git'
  ])('accepts %s', (url) => {
    expect(gitUrlProblem(url)).toBeNull()
  })

  it.each([
    ['', 'empty'],
    ['has space.git', 'spaces'],
    ['-uhttps://x', 'spaces'],
    ['ftp://example.com/notes.git', 'scheme'],
    ['https://you:token@github.com/you/notes.git', 'password'],
    ['notes', 'shape'],
    ['relative/path.git', 'shape'],
    ['https:///x.git', 'shape']
  ])('refuses %s as %s', (url, problem) => {
    expect(gitUrlProblem(url)).toBe(problem)
  })
})

describe('folderNameProblem', () => {
  it('accepts ordinary names and refuses the rest', () => {
    expect(folderNameProblem('notes')).toBeNull()
    expect(folderNameProblem('Team notes 2026')).toBeNull()
    expect(folderNameProblem(' ')).toBe('empty')
    expect(folderNameProblem('a/b')).toBe('characters')
    expect(folderNameProblem('notes.')).toBe('characters')
    expect(folderNameProblem('..')).toBe('characters')
    expect(folderNameProblem('NUL')).toBe('reserved')
  })
})
