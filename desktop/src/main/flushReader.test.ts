import { describe, expect, it } from 'vitest'
import { flushReaderActions, type ReaderWindow } from './flushReader'

function readerWindow(
  answer: () => Promise<unknown>,
  destroyed = false
): ReaderWindow & { scripts: string[] } {
  const scripts: string[] = []
  return {
    scripts,
    isDestroyed: () => destroyed,
    webContents: {
      executeJavaScript: (code: string) => {
        scripts.push(code)
        return answer()
      }
    }
  }
}

describe('flushReaderActions', () => {
  it('asks the reader to write what waits for Undo and resolves with how many it wrote', async () => {
    const window = readerWindow(() => Promise.resolve(2))
    await expect(flushReaderActions(window)).resolves.toBe(2)
    expect(window.scripts).toHaveLength(1)
    expect(window.scripts[0]).toContain('kosFlushPendingActions')
  })

  it('does nothing without a window or with a destroyed one', async () => {
    await expect(flushReaderActions(null)).resolves.toBeNull()
    const gone = readerWindow(() => Promise.resolve(1), true)
    await expect(flushReaderActions(gone)).resolves.toBeNull()
    expect(gone.scripts).toHaveLength(0)
  })

  it('never rejects, and gives up after the timeout', async () => {
    await expect(
      flushReaderActions(readerWindow(() => Promise.reject(new Error('gone'))))
    ).resolves.toBeNull()
    const started = Date.now()
    const hanging = readerWindow(() => new Promise(() => undefined))
    await expect(flushReaderActions(hanging, 30)).resolves.toBeNull()
    expect(Date.now() - started).toBeLessThan(2000)
  })
})
