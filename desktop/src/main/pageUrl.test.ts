import { join } from 'path'
import { pathToFileURL } from 'url'
import { describe, expect, it } from 'vitest'
import { pageUrl } from './pageUrl'

describe('pageUrl', () => {
  it('uses the dev server root for the start page and its pages beside it', () => {
    expect(pageUrl('index', 'http://localhost:5173/', '/unused')).toBe('http://localhost:5173/')
    expect(pageUrl('referat', 'http://localhost:5173//', '/unused')).toBe(
      'http://localhost:5173/referat.html'
    )
    expect(pageUrl('clone', 'http://localhost:5173', '/unused')).toBe(
      'http://localhost:5173/clone.html'
    )
  })

  it('uses the built files without a dev server', () => {
    const dir = join('/app', 'out', 'renderer')
    expect(pageUrl('index', null, dir)).toBe(pathToFileURL(join(dir, 'index.html')).href)
    expect(pageUrl('clone', null, dir)).toBe(pathToFileURL(join(dir, 'clone.html')).href)
    expect(pageUrl('referat', null, dir)).toMatch(/^file:\/\/.*\/out\/renderer\/referat\.html$/)
  })
})
