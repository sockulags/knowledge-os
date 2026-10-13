/* eslint-disable @typescript-eslint/explicit-function-return-type -- plain JavaScript, no types to declare */

import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'fs'
import { tmpdir } from 'os'
import { dirname, join } from 'path'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { findDependencyProblems, formatProblems } from './check-deps.mjs'

const GIT_A = 'git+ssh://git@github.com/owner/sdk.git#aaaaaaa'
const GIT_B = 'git+ssh://git@github.com/owner/sdk.git#bbbbbbb'

let dir = ''

function write(path, value) {
  const full = join(dir, path)
  mkdirSync(dirname(full), { recursive: true })
  writeFileSync(full, JSON.stringify(value))
}

function install(name, version) {
  write(`node_modules/${name}/package.json`, { name, version })
}

beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), 'kos-check-deps-'))
  write('package.json', {
    dependencies: { left: '^1.0.0' },
    devDependencies: { sdk: 'github:owner/sdk#v0.1.0' }
  })
  write('package-lock.json', {
    lockfileVersion: 3,
    packages: {
      'node_modules/left': { version: '1.2.0' },
      'node_modules/sdk': { version: '0.1.0', resolved: GIT_A }
    }
  })
})

afterEach(() => {
  rmSync(dir, { recursive: true, force: true })
})

describe('findDependencyProblems', () => {
  it('reports nothing when every dependency is installed as locked', () => {
    install('left', '1.2.0')
    install('sdk', '0.1.0')
    write('node_modules/.package-lock.json', {
      packages: { 'node_modules/sdk': { resolved: GIT_A } }
    })
    expect(findDependencyProblems(dir)).toEqual([])
  })

  it('reports every declared dependency that is not in node_modules', () => {
    expect(findDependencyProblems(dir)).toEqual([
      { name: 'left', reason: 'not installed' },
      { name: 'sdk', reason: 'not installed' }
    ])
  })

  it('reports an installed version that differs from package-lock.json', () => {
    install('left', '1.1.0')
    install('sdk', '0.1.0')
    expect(findDependencyProblems(dir)).toEqual([
      { name: 'left', reason: 'installed 1.1.0, package-lock.json wants 1.2.0' }
    ])
  })

  it('reports a git dependency installed from another commit', () => {
    install('left', '1.2.0')
    install('sdk', '0.1.0')
    write('node_modules/.package-lock.json', {
      packages: { 'node_modules/sdk': { resolved: GIT_B } }
    })
    expect(findDependencyProblems(dir)).toEqual([
      { name: 'sdk', reason: `installed from ${GIT_B}, package-lock.json wants ${GIT_A}` }
    ])
  })

  it('skips the commit check when npm left no hidden lockfile', () => {
    install('left', '1.2.0')
    install('sdk', '0.1.0')
    expect(findDependencyProblems(dir)).toEqual([])
  })

  it('checks only presence when there is no package-lock.json', () => {
    rmSync(join(dir, 'package-lock.json'))
    install('left', '0.0.1')
    expect(findDependencyProblems(dir)).toEqual([{ name: 'sdk', reason: 'not installed' }])
  })
})

describe('formatProblems', () => {
  it('names each package and says to run npm install in desktop/', () => {
    const message = formatProblems([{ name: 'sdk', reason: 'not installed' }])
    expect(message).toContain('  - sdk: not installed')
    expect(message).toContain('Run `npm install` in desktop/')
  })
})
