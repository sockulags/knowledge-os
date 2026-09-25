import { describe, expect, it } from 'vitest'
import { firstIndex, lastIndex, letterIndex, stepIndex, titleParts } from './menuNav'

const items = [
  { type: 'normal', enabled: true, label: 'Open' },
  { type: 'separator', enabled: false, label: '' },
  { type: 'normal', enabled: false, label: 'Close' },
  { type: 'checkbox', enabled: true, label: 'Reopen' },
  { type: 'normal', enabled: true, label: 'Exit' }
]

describe('stepIndex', () => {
  it('skips separators and disabled items and wraps around', () => {
    expect(stepIndex(items, 0, 1)).toBe(3)
    expect(stepIndex(items, 3, -1)).toBe(0)
    expect(stepIndex(items, 4, 1)).toBe(0)
    expect(stepIndex(items, 0, -1)).toBe(4)
    expect(firstIndex(items)).toBe(0)
    expect(lastIndex(items)).toBe(4)
  })

  it('finds nothing in an empty or all-disabled menu', () => {
    expect(stepIndex([], -1, 1)).toBe(-1)
    expect(firstIndex([{ type: 'normal', enabled: false }])).toBe(-1)
  })
})

describe('letterIndex', () => {
  it('jumps to the next item starting with the letter', () => {
    expect(letterIndex(items, 'e')).toBe(4)
    expect(letterIndex(items, 'O')).toBe(0)
    expect(letterIndex(items, 'c')).toBe(-1)
    expect(letterIndex(items, 'Enter')).toBe(-1)
  })
})

describe('titleParts', () => {
  it('splits the reader title into page and knowledge base', () => {
    expect(titleParts('Home — field-notes — Knowledge OS', 'field-notes')).toEqual({
      page: 'Home',
      workspace: 'field-notes'
    })
    expect(titleParts('field-notes — Knowledge OS', 'field-notes')).toEqual({
      page: '',
      workspace: 'field-notes'
    })
    expect(titleParts('Knowledge OS', null)).toEqual({ page: '', workspace: '' })
    expect(titleParts('Clone Knowledge Base', null)).toEqual({
      page: 'Clone Knowledge Base',
      workspace: ''
    })
  })
})
