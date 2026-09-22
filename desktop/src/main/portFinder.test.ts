import { createServer } from 'net'
import { describe, expect, it } from 'vitest'
import { findFreePort } from './portFinder'

function listen(port: number): Promise<() => Promise<void>> {
  return new Promise((resolve, reject) => {
    const server = createServer()
    server.on('error', reject)
    server.listen({ host: '127.0.0.1', port, exclusive: true }, () =>
      resolve(() => new Promise((done) => server.close(() => done())))
    )
  })
}

describe('findFreePort', () => {
  it('returns a non-privileged port that can be bound right away', async () => {
    const port = await findFreePort()
    expect(port).toBeGreaterThan(1024)
    expect(port).toBeLessThan(65536)
    const close = await listen(port)
    await close()
  })

  it('never returns a port that is currently taken', async () => {
    const taken = await findFreePort()
    const close = await listen(taken)
    try {
      const ports = await Promise.all(Array.from({ length: 5 }, () => findFreePort()))
      expect(ports).not.toContain(taken)
    } finally {
      await close()
    }
  })
})
