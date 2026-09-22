import { describe, expect, it } from 'vitest'
import { decideNavigation } from './navigation'

const core = 'http://127.0.0.1:53111'
const startPage = 'file:///C:/app/out/renderer/index.html'

describe('decideNavigation', () => {
  it('allows any path on the running core', () => {
    expect(decideNavigation(`${core}/r/some-record?x=1#top`, [startPage, core])).toBe('allow')
  })

  it('allows the start page itself but no other local file', () => {
    expect(decideNavigation(startPage, [startPage, null])).toBe('allow')
    expect(decideNavigation('file:///C:/Windows/win.ini', [startPage, core])).toBe('block')
  })

  it('treats another local port as a foreign origin', () => {
    expect(decideNavigation('http://127.0.0.1:8800/', [startPage, core])).toBe('open-external')
  })

  it('hands web links to the system browser', () => {
    expect(decideNavigation('https://example.com/page', [startPage, core])).toBe('open-external')
  })

  it('blocks other schemes and unparsable URLs', () => {
    expect(decideNavigation('javascript:alert(1)', [startPage, core])).toBe('block')
    expect(decideNavigation('ms-settings:privacy', [startPage, core])).toBe('block')
    expect(decideNavigation('not a url', [startPage, core])).toBe('block')
  })
})
