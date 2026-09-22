import { join } from 'path'
import { describe, expect, it } from 'vitest'
import { findRepoRoot, interpreterCandidates, venvPython } from './pythonInterpreter'

const repo = join('C:', 'code', 'knowledge-os')
const winVenv = venvPython(repo, 'win32')

function commands(options: Parameters<typeof interpreterCandidates>[0]): string[] {
  return interpreterCandidates(options).map((c) => [c.command, ...c.args].join(' '))
}

describe('interpreterCandidates', () => {
  it('uses only KOS_PYTHON when it is set, even if the venv exists', () => {
    const candidates = interpreterCandidates({
      env: { KOS_PYTHON: ' D:\\py\\python.exe ' },
      repoRoot: repo,
      platform: 'win32',
      exists: () => true
    })
    expect(candidates).toEqual([{ command: 'D:\\py\\python.exe', args: [], source: 'KOS_PYTHON' }])
  })

  it('ignores an empty KOS_PYTHON', () => {
    expect(
      commands({ env: { KOS_PYTHON: '' }, repoRoot: null, platform: 'win32', exists: () => false })
    ).toEqual(['py -3.11', 'python'])
  })

  it('prefers the repository .venv, then py -3.11, then python on Windows', () => {
    const checked: string[] = []
    const result = commands({
      env: {},
      repoRoot: repo,
      platform: 'win32',
      exists: (path) => {
        checked.push(path)
        return path === winVenv
      }
    })
    expect(result).toEqual([winVenv, 'py -3.11', 'python'])
    expect(checked).toEqual([winVenv])
    expect(winVenv).toBe(join(repo, '.venv', 'Scripts', 'python.exe'))
  })

  it('skips a missing .venv', () => {
    expect(commands({ env: {}, repoRoot: repo, platform: 'win32', exists: () => false })).toEqual([
      'py -3.11',
      'python'
    ])
  })

  it('uses bin/python and python3 names elsewhere', () => {
    const venv = venvPython(repo, 'linux')
    expect(venv).toBe(join(repo, '.venv', 'bin', 'python'))
    expect(
      commands({ env: {}, repoRoot: repo, platform: 'linux', exists: (path) => path === venv })
    ).toEqual([venv, 'python3.11', 'python3', 'python'])
  })
})

describe('findRepoRoot', () => {
  const appPath = join(repo, 'desktop')

  it('recognizes the checkout above desktop/', () => {
    const present = new Set([
      join(repo, 'pyproject.toml'),
      join(repo, 'knowledge_os', 'reader', '__init__.py')
    ])
    expect(findRepoRoot(appPath, (path) => present.has(path))).toBe(repo)
  })

  it('returns null outside a checkout', () => {
    expect(findRepoRoot(appPath, (path) => path.endsWith('pyproject.toml'))).toBeNull()
  })
})
