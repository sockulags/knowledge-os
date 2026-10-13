import { existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'
import { afterEach, describe, expect, it } from 'vitest'
import {
  AdapterInstallError,
  checkLock,
  extractPackage,
  installAdapter,
  installedEntry
} from './installer'
import { fakeRegistry, tarball } from './testing/tarball'

const roots: string[] = []
afterEach(() => {
  while (roots.length > 0) rmSync(roots.pop()!, { recursive: true, force: true })
})
function root(): string {
  const folder = mkdtempSync(join(tmpdir(), 'kos-adapters-'))
  roots.push(folder)
  return folder
}

const PACKAGES = {
  'node_modules/@acme/agent-acp': {
    'package.json': '{"name":"@acme/agent-acp"}',
    'dist/index.js': 'console.log(1)'
  },
  'node_modules/zod': { 'package.json': '{"name":"zod"}', 'index.js': 'module.exports = {}' },
  'node_modules/@acme/agent-acp/node_modules/zod': {
    'package.json': '{"name":"zod","version":"3"}'
  }
}

describe('installAdapter', () => {
  it('installs every locked package, reports progress, and does it only once', async () => {
    const target = root()
    const { lock, fetchBytes, fetched } = fakeRegistry('@acme/agent-acp', '1.2.0', PACKAGES)
    const progress: number[] = []
    const entry = await installAdapter(lock, target, fetchBytes, ({ done }) => progress.push(done))

    expect(entry).toBe(
      join(target, 'agent-acp@1.2.0', 'node_modules', '@acme', 'agent-acp', 'dist', 'index.js')
    )
    expect(readFileSync(entry, 'utf8')).toBe('console.log(1)')
    expect(
      existsSync(
        join(
          target,
          'agent-acp@1.2.0',
          'node_modules',
          '@acme',
          'agent-acp',
          'node_modules',
          'zod',
          'package.json'
        )
      )
    ).toBe(true)
    expect(progress.at(0)).toBe(0)
    expect(progress.at(-1)).toBe(3)
    expect(installedEntry(lock, target)).toBe(entry)

    await installAdapter(lock, target, fetchBytes)
    expect(fetched).toHaveLength(3)
  })

  it('refuses a tarball that does not match its hash and leaves nothing behind', async () => {
    const target = root()
    const { lock, fetchBytes } = fakeRegistry('@acme/agent-acp', '1.2.0', PACKAGES)
    lock.packages[1] = {
      ...lock.packages[1],
      integrity: 'sha512-' + Buffer.alloc(64).toString('base64')
    }
    await expect(installAdapter(lock, target, fetchBytes)).rejects.toThrow(/integrity hash/)
    expect(readdirSync(target)).toEqual([])
    expect(installedEntry(lock, target)).toBeNull()
  })

  it('leaves nothing behind when a download fails', async () => {
    const target = root()
    const { lock, fetchBytes } = fakeRegistry('@acme/agent-acp', '1.2.0', PACKAGES)
    const failing = async (url: string): Promise<Uint8Array> => {
      if (url.includes('zod')) throw new Error('connection reset')
      return fetchBytes(url)
    }
    await expect(installAdapter(lock, target, failing)).rejects.toThrow(
      /could not download zod@1\.2\.0: connection reset/
    )
    expect(readdirSync(target)).toEqual([])
  })

  it('replaces an earlier version of the same adapter', async () => {
    const target = root()
    const old = fakeRegistry('@acme/agent-acp', '1.1.0', PACKAGES)
    await installAdapter(old.lock, target, old.fetchBytes)
    mkdirSync(join(target, '.staging-agent-acp@1.1.0-dead'))
    const next = fakeRegistry('@acme/agent-acp', '1.2.0', PACKAGES)
    await installAdapter(next.lock, target, next.fetchBytes)
    expect(readdirSync(target)).toEqual(['agent-acp@1.2.0'])
    expect(installedEntry(old.lock, target)).toBeNull()
  })

  it('does not count a folder with a different lock as installed', async () => {
    const target = root()
    const { lock, fetchBytes } = fakeRegistry('@acme/agent-acp', '1.2.0', PACKAGES)
    await installAdapter(lock, target, fetchBytes)
    const changed = { ...lock, packages: lock.packages.slice(0, 2) }
    expect(installedEntry(changed, target)).toBeNull()
  })
})

describe('checkLock', () => {
  const { lock } = fakeRegistry('@acme/agent-acp', '1.2.0', PACKAGES)

  it('accepts only https tarballs from the npm registry with sha512 hashes and node_modules paths', () => {
    expect(() => checkLock(lock)).not.toThrow()
    const bad = (change: Partial<(typeof lock.packages)[number]>): void =>
      checkLock({ ...lock, packages: [lock.packages[0], { ...lock.packages[1], ...change }] })
    expect(() => bad({ resolved: 'http://registry.npmjs.org/x.tgz' })).toThrow(AdapterInstallError)
    expect(() => bad({ resolved: 'https://evil.example/x.tgz' })).toThrow(/only fetched from/)
    expect(() => bad({ integrity: 'sha1-abc' })).toThrow(/sha512/)
    expect(() => bad({ path: 'node_modules/../../etc' })).toThrow(/node_modules path/)
    expect(() => checkLock({ ...lock, version: '9.9.9' })).toThrow(/does not contain/)
  })
})

describe('extractPackage', () => {
  it('refuses a tarball entry that escapes the package folder', () => {
    const target = root()
    expect(() =>
      extractPackage(tarball({}, ['package/../../evil.txt']), join(target, 'pkg'))
    ).toThrow(/unsafe path/)
    expect(existsSync(join(target, 'evil.txt'))).toBe(false)
  })

  it('reads long file names', () => {
    const target = root()
    const long = `dist/${'a'.repeat(120)}.js`
    extractPackage(tarball({ [long]: 'x' }), target)
    expect(readFileSync(join(target, ...long.split('/')), 'utf8')).toBe('x')
  })
})
