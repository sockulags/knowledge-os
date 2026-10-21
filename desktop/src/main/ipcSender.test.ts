import { describe, expect, it } from 'vitest'
import { isFrom, isPage, type SenderEvent, type SenderWindow } from './ipcSender'

const page = 'file:///C:/app/out/renderer/clone.html'

function fakeWindow(
  destroyed = false
): SenderWindow & { webContents: { mainFrame: { url: string } } } {
  return { isDestroyed: () => destroyed, webContents: { mainFrame: { url: page } } }
}

function eventFrom(window: ReturnType<typeof fakeWindow>): SenderEvent {
  return { sender: window.webContents, senderFrame: window.webContents.mainFrame }
}

const any = (): boolean => true

describe('isFrom', () => {
  it('accepts the main frame of the window at an allowed URL', () => {
    const window = fakeWindow()
    expect(isFrom(eventFrom(window), window, isPage(page))).toBe(true)
  })

  it('rejects a URL the handler does not allow', () => {
    const window = fakeWindow()
    expect(isFrom(eventFrom(window), window, () => false)).toBe(false)
  })

  it('rejects another window, even at the same URL', () => {
    const own = fakeWindow()
    const other = fakeWindow()
    expect(isFrom(eventFrom(other), own, any)).toBe(false)
  })

  it('rejects a subframe of the window', () => {
    const window = fakeWindow()
    const event = { sender: window.webContents, senderFrame: { url: page } }
    expect(isFrom(event, window, any)).toBe(false)
  })

  it('rejects a missing frame, a missing window, and a destroyed window', () => {
    const window = fakeWindow()
    expect(isFrom({ sender: window.webContents, senderFrame: null }, window, any)).toBe(false)
    expect(isFrom(eventFrom(window), null, any)).toBe(false)
    const destroyed = fakeWindow(true)
    expect(isFrom(eventFrom(destroyed), destroyed, any)).toBe(false)
  })
})

describe('isPage', () => {
  it('matches the page with or without a query or fragment, and nothing else', () => {
    const own = isPage(page)
    expect(own(page)).toBe(true)
    expect(own(`${page}?x=1#top`)).toBe(true)
    expect(own('file:///C:/app/out/renderer/index.html')).toBe(false)
  })
})
