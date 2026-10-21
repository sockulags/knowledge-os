import { existsSync, mkdtempSync, readFileSync, readdirSync, rmSync, statSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { formatLine, initLog, log, logDir, RotatingLogFile } from './logger'

let dir: string

beforeEach(() => {
  dir = join(mkdtempSync(join(tmpdir(), 'kos-log-')), 'logs')
})

afterEach(() => {
  rmSync(join(dir, '..'), { recursive: true, force: true })
  vi.restoreAllMocks()
})

describe('RotatingLogFile', () => {
  it('creates the folder and appends lines', () => {
    const file = new RotatingLogFile({ dir })
    file.write('one')
    file.write('two\n')
    expect(readFileSync(join(dir, 'main.log'), 'utf-8')).toBe('one\ntwo\n')
  })

  it('starts a new file before one would pass the limit and keeps three files', () => {
    const file = new RotatingLogFile({ dir, maxBytes: 20, keptOld: 2 })
    // Each line is 10 bytes, so every file holds two.
    for (let i = 0; i < 10; i++) file.write(`line ${i}...`)
    expect(readdirSync(dir).sort()).toEqual(['main.log', 'main.log.1', 'main.log.2'])
    expect(readFileSync(join(dir, 'main.log'), 'utf-8')).toBe('line 8...\nline 9...\n')
    expect(readFileSync(join(dir, 'main.log.1'), 'utf-8')).toBe('line 6...\nline 7...\n')
    expect(readFileSync(join(dir, 'main.log.2'), 'utf-8')).toBe('line 4...\nline 5...\n')
    for (const name of readdirSync(dir)) expect(statSync(join(dir, name)).size).toBeLessThan(21)
  })

  it('writes a line longer than the limit into a file of its own', () => {
    const file = new RotatingLogFile({ dir, maxBytes: 8 })
    file.write('a much longer line')
    expect(readFileSync(join(dir, 'main.log'), 'utf-8')).toBe('a much longer line\n')
    expect(existsSync(join(dir, 'main.log.1'))).toBe(false)
  })
})

describe('formatLine', () => {
  it('puts time and level before the message, formatted like the console', () => {
    const line = formatLine('error', ['could not save', new Error('disk full')], new Date(0))
    expect(line.startsWith('1970-01-01T00:00:00.000Z ERROR could not save Error: disk full')).toBe(
      true
    )
    expect(formatLine('info', ['%s ready', 'core'], new Date(0))).toBe(
      '1970-01-01T00:00:00.000Z INFO  core ready'
    )
  })
})

describe('log', () => {
  it('writes to the console and, once started, to main.log', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined)
    initLog(dir)
    expect(logDir()).toBe(dir)
    log.error('could not save', 'the settings')
    expect(consoleError).toHaveBeenCalledWith('could not save', 'the settings')
    expect(readFileSync(join(dir, 'main.log'), 'utf-8')).toMatch(
      /^\S+ ERROR could not save the settings\n$/
    )
  })
})
