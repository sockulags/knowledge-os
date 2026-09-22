// Picks a free local TCP port for the Python core. The operating system
// assigns it (bind to port 0), so no range is guessed or probed. Another
// process could still take the port before the core binds it; pythonCore.ts
// retries with a new port when that happens.

import { createServer } from 'net'

export function findFreePort(host = '127.0.0.1'): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = createServer()
    server.unref()
    server.on('error', reject)
    server.listen({ host, port: 0, exclusive: true }, () => {
      const address = server.address()
      if (address === null || typeof address === 'string') {
        server.close(() => reject(new Error('could not determine a free port')))
        return
      }
      server.close(() => resolve(address.port))
    })
  })
}
