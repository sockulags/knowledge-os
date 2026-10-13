// Builds npm-style package tarballs (gzipped tar, files under `package/`) in
// memory, and a lock for them, so the installer is tested without a network.

import { createHash } from 'crypto'
import { gzipSync } from 'zlib'
import type { AdapterLock } from '../installer'

function header(name: string, size: number, type: string, mode: number): Buffer {
  const block = Buffer.alloc(512, 0)
  block.write(name.slice(0, 100), 0, 'utf8')
  block.write(mode.toString(8).padStart(7, '0') + '\0', 100, 'ascii')
  block.write('0000000\0', 108, 'ascii')
  block.write('0000000\0', 116, 'ascii')
  block.write(size.toString(8).padStart(11, '0') + '\0', 124, 'ascii')
  block.write('00000000000\0', 136, 'ascii')
  block.write(type, 156, 'ascii')
  block.write('ustar\0', 257, 'ascii')
  block.write('00', 263, 'ascii')
  block.fill(' ', 148, 156)
  let sum = 0
  for (const byte of block) sum += byte
  block.write(sum.toString(8).padStart(6, '0') + '\0 ', 148, 'ascii')
  return block
}

/** A gzipped tar with `files` (path inside the package → content). */
export function tarball(files: Record<string, string>, rawNames: string[] = []): Buffer {
  const parts: Buffer[] = []
  const add = (name: string, content: string, mode = 0o644): void => {
    const body = Buffer.from(content)
    if (name.length > 100) {
      const long = Buffer.from(name + '\0')
      parts.push(
        header('././@LongLink', long.length, 'L', 0o644),
        long,
        Buffer.alloc((512 - (long.length % 512)) % 512)
      )
    }
    parts.push(
      header(name, body.length, '0', mode),
      body,
      Buffer.alloc((512 - (body.length % 512)) % 512)
    )
  }
  for (const [path, content] of Object.entries(files))
    add(`package/${path}`, content, path.endsWith('.sh') ? 0o755 : 0o644)
  // Names written as given, to test unsafe paths.
  for (const name of rawNames) add(name, 'x')
  parts.push(Buffer.alloc(1024, 0))
  return gzipSync(Buffer.concat(parts))
}

export function integrity(bytes: Uint8Array): string {
  return `sha512-${createHash('sha512').update(bytes).digest('base64')}`
}

/** A lock for `packages` (install path → files), and a fetch that serves their tarballs. */
export function fakeRegistry(
  packageName: string,
  version: string,
  packages: Record<string, Record<string, string>>
): { lock: AdapterLock; fetchBytes: (url: string) => Promise<Uint8Array>; fetched: string[] } {
  const served = new Map<string, Buffer>()
  const lock: AdapterLock = { packageName, version, entry: 'dist/index.js', packages: [] }
  for (const [path, files] of Object.entries(packages)) {
    const bytes = tarball(files)
    const url = `https://registry.npmjs.org/${path.replace(/^node_modules\//, '')}/-/pkg-${version}.tgz`
    served.set(url, bytes)
    lock.packages.push({ path, version, resolved: url, integrity: integrity(bytes) })
  }
  const fetched: string[] = []
  return {
    lock,
    fetched,
    fetchBytes: async (url) => {
      fetched.push(url)
      const bytes = served.get(url)
      if (bytes === undefined) throw new Error(`404 ${url}`)
      return bytes
    }
  }
}
