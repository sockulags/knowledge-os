// Installs an ACP adapter on demand, from its lock (adapters/*.lock.json,
// written by scripts/lock-adapter.mjs): every npm package in the adapter's
// dependency tree at the exact version tested, each tarball checked against
// its sha512 integrity hash before anything is written.
//
// The app does not ship the adapters: the Claude adapter depends on
// Anthropic's proprietary Claude Agent SDK, which the person fetches from npm
// themselves this way, as `npx` would. Nothing is run while installing (no
// install scripts), and optional platform binaries are never fetched.
//
// An install is written to a staging folder and renamed into place only when
// complete, with a marker file last, so a folder that exists is a whole
// install; a failure removes the staging folder. Only Node built-ins are
// imported, and the download is injected, so this is unit-testable.

import { createHash, randomBytes } from 'crypto'
import {
  chmodSync,
  existsSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  renameSync,
  rmSync,
  writeFileSync
} from 'fs'
import { dirname, join, posix, resolve, sep } from 'path'
import { gunzipSync } from 'zlib'

export interface LockedPackage {
  /** Where it goes in the install, e.g. `node_modules/zod`. */
  path: string
  version: string
  /** The tarball URL. */
  resolved: string
  /** `sha512-<base64>`. */
  integrity: string
}

export interface AdapterLock {
  packageName: string
  version: string
  /** The adapter's entry file inside its package, run with Node. */
  entry: string
  packages: LockedPackage[]
}

/** Fetches a URL's bytes; in the app, Electron's net.fetch, which uses the system proxy. */
export type FetchBytes = (url: string) => Promise<Uint8Array>

export interface InstallProgress {
  done: number
  total: number
}

const MARKER = '.kos-adapter.json'
const PARALLEL = 6
const ALLOWED_HOST = 'registry.npmjs.org'

export class AdapterInstallError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'AdapterInstallError'
  }
}

/** The folder name of one adapter version, e.g. `claude-agent-acp@0.81.2`. */
export function installFolderName(lock: AdapterLock): string {
  return `${lock.packageName.split('/').pop()}@${lock.version}`
}

function lockDigest(lock: AdapterLock): string {
  return createHash('sha256').update(JSON.stringify(lock.packages)).digest('hex')
}

/** The installed adapter's entry file, or null when this exact lock is not installed. */
export function installedEntry(lock: AdapterLock, root: string): string | null {
  const folder = join(root, installFolderName(lock))
  try {
    const marker = JSON.parse(readFileSync(join(folder, MARKER), 'utf8')) as { lock?: string }
    if (marker.lock !== lockDigest(lock)) return null
  } catch {
    return null
  }
  const entry = join(
    folder,
    'node_modules',
    ...lock.packageName.split('/'),
    ...lock.entry.split('/')
  )
  return existsSync(entry) ? entry : null
}

/** Checks a lock before anything is fetched: https tarballs from npm, sha512 hashes, safe paths. */
export function checkLock(lock: AdapterLock): void {
  if (
    !lock.packages.some(
      (item) => item.path === `node_modules/${lock.packageName}` && item.version === lock.version
    )
  ) {
    throw new AdapterInstallError(`the lock does not contain ${lock.packageName}@${lock.version}`)
  }
  for (const item of lock.packages) {
    let url: URL
    try {
      url = new URL(item.resolved)
    } catch {
      throw new AdapterInstallError(`${item.path}: ${item.resolved} is not a URL`)
    }
    if (url.protocol !== 'https:' || url.hostname !== ALLOWED_HOST) {
      throw new AdapterInstallError(
        `${item.path}: packages are only fetched from https://${ALLOWED_HOST}`
      )
    }
    if (!/^sha512-[A-Za-z0-9+/]+=*$/.test(item.integrity)) {
      throw new AdapterInstallError(`${item.path}: missing sha512 integrity`)
    }
    const parts = item.path.split('/')
    if (
      parts[0] !== 'node_modules' ||
      parts.some((part) => part === '' || part === '.' || part === '..')
    ) {
      throw new AdapterInstallError(`${item.path}: not a node_modules path`)
    }
  }
}

function verify(bytes: Uint8Array, integrity: string, what: string): void {
  const expected = integrity.slice('sha512-'.length)
  const actual = createHash('sha512').update(bytes).digest('base64')
  if (actual !== expected) {
    throw new AdapterInstallError(
      `${what} does not match its integrity hash; nothing was installed`
    )
  }
}

function readString(block: Buffer, offset: number, length: number): string {
  const slice = block.subarray(offset, offset + length)
  const end = slice.indexOf(0)
  return slice.subarray(0, end === -1 ? slice.length : end).toString('utf8')
}

function readOctal(block: Buffer, offset: number, length: number): number {
  const text = readString(block, offset, length).trim()
  return text === '' ? 0 : parseInt(text, 8)
}

/** Extracts an npm tarball (gzipped tar, entries under `package/`) into `target`. */
export function extractPackage(tgz: Uint8Array, target: string): void {
  const tar = gunzipSync(tgz)
  const base = resolve(target)
  let offset = 0
  let longName: string | null = null
  let paxPath: string | null = null
  while (offset + 512 <= tar.length) {
    const header = tar.subarray(offset, offset + 512)
    if (header.every((byte) => byte === 0)) break
    const size = readOctal(header, 124, 12)
    const type = String.fromCharCode(header[156] || 48)
    const bodyStart = offset + 512
    const body = tar.subarray(bodyStart, bodyStart + size)
    offset = bodyStart + Math.ceil(size / 512) * 512

    if (type === 'L') {
      longName = readString(body, 0, body.length)
      continue
    }
    if (type === 'x') {
      const match = /\d+ path=([^\n]*)\n/.exec(body.toString('utf8'))
      paxPath = match ? match[1] : null
      continue
    }
    if (type === 'g') continue
    const prefix = readString(header, 345, 155)
    const name =
      paxPath ??
      longName ??
      (prefix ? `${prefix}/${readString(header, 0, 100)}` : readString(header, 0, 100))
    longName = null
    paxPath = null
    // npm packs every file under one top folder, usually `package/`.
    const inside = name.split('/').slice(1).join('/')
    if (inside === '' || (type !== '0' && type !== '5' && type !== '\0')) continue
    const normalized = posix.normalize(inside)
    const destination = resolve(base, ...normalized.split('/'))
    if (
      normalized.startsWith('..') ||
      posix.isAbsolute(normalized) ||
      !destination.startsWith(base + sep)
    ) {
      throw new AdapterInstallError(`a package contains an unsafe path: ${name}`)
    }
    if (type === '5') {
      mkdirSync(destination, { recursive: true })
      continue
    }
    mkdirSync(dirname(destination), { recursive: true })
    writeFileSync(destination, body)
    const mode = readOctal(header, 100, 8)
    if (process.platform !== 'win32' && mode & 0o111) chmodSync(destination, 0o755)
  }
}

/**
 * Install one adapter version into `root/<name>@<version>` unless it is
 * already there, and remove other versions of the same adapter. Resolves to
 * the adapter's entry file.
 */
export async function installAdapter(
  lock: AdapterLock,
  root: string,
  fetchBytes: FetchBytes,
  onProgress: (progress: InstallProgress) => void = () => undefined
): Promise<string> {
  const existing = installedEntry(lock, root)
  if (existing !== null) return existing
  checkLock(lock)
  mkdirSync(root, { recursive: true })
  const folder = join(root, installFolderName(lock))
  const staging = join(
    root,
    `.staging-${installFolderName(lock)}-${randomBytes(4).toString('hex')}`
  )
  const total = lock.packages.length
  let done = 0
  onProgress({ done, total })
  try {
    const queue = [...lock.packages]
    const worker = async (): Promise<void> => {
      for (let item = queue.shift(); item !== undefined; item = queue.shift()) {
        let bytes: Uint8Array
        try {
          bytes = await fetchBytes(item.resolved)
        } catch (error) {
          throw new AdapterInstallError(
            `could not download ${item.path.replace(/^.*node_modules\//, '')}@${item.version}: ${
              error instanceof Error ? error.message : String(error)
            }`
          )
        }
        verify(
          bytes,
          item.integrity,
          `${item.path.replace(/^.*node_modules\//, '')}@${item.version}`
        )
        extractPackage(bytes, join(staging, ...item.path.split('/')))
        done += 1
        onProgress({ done, total })
      }
    }
    await Promise.all(Array.from({ length: Math.min(PARALLEL, total) }, worker))
    writeFileSync(
      join(staging, MARKER),
      JSON.stringify(
        { packageName: lock.packageName, version: lock.version, lock: lockDigest(lock) },
        null,
        2
      )
    )
    rmSync(folder, { recursive: true, force: true })
    renameSync(staging, folder)
  } catch (error) {
    rmSync(staging, { recursive: true, force: true })
    throw error
  }
  // Earlier versions of this adapter, and staging folders a crash left behind.
  const prefix = `${lock.packageName.split('/').pop()}@`
  for (const name of readdirSync(root)) {
    const stale =
      (name.startsWith(prefix) && name !== installFolderName(lock)) ||
      name.startsWith(`.staging-${prefix}`)
    if (stale) rmSync(join(root, name), { recursive: true, force: true })
  }
  const entry = installedEntry(lock, root)
  if (entry === null)
    throw new AdapterInstallError(
      `${lock.packageName} was installed without its entry file ${lock.entry}`
    )
  return entry
}
