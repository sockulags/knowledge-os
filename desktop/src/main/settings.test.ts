import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { DEFAULT_SETTINGS, loadSettings, saveSettings } from './settings'

describe('loadSettings and saveSettings', () => {
  let dir: string
  let file: string

  beforeEach(() => {
    dir = mkdtempSync(join(tmpdir(), 'kos-settings-'))
    file = join(dir, 'nested', 'settings.json')
  })

  afterEach(() => {
    rmSync(dir, { recursive: true, force: true })
  })

  it('checks for updates and reopens the last knowledge base by default when there is no file', () => {
    expect(loadSettings(file)).toEqual({ checkForUpdates: true, reopenLastWorkspace: true })
  })

  it('round-trips a turned-off automatic check', () => {
    saveSettings(file, { checkForUpdates: false, reopenLastWorkspace: true })
    expect(loadSettings(file)).toEqual({ checkForUpdates: false, reopenLastWorkspace: true })
    expect(JSON.parse(readFileSync(file, 'utf-8')).version).toBe(1)
  })

  it('round-trips a turned-off reopen', () => {
    saveSettings(file, { checkForUpdates: true, reopenLastWorkspace: false })
    expect(loadSettings(file)).toEqual({ checkForUpdates: true, reopenLastWorkspace: false })
    expect(JSON.parse(readFileSync(file, 'utf-8')).reopenLastWorkspace).toBe(false)
  })

  it('reopens by default when a file from an older version lacks the setting', () => {
    const older = join(dir, 'older.json')
    writeFileSync(older, JSON.stringify({ version: 1, checkForUpdates: false }), 'utf-8')
    expect(loadSettings(older)).toEqual({ checkForUpdates: false, reopenLastWorkspace: true })
  })

  it('falls back to the defaults for a damaged file', () => {
    const damaged = join(dir, 'damaged.json')
    writeFileSync(damaged, '{"checkForUpdates": fal', 'utf-8')
    expect(loadSettings(damaged)).toEqual(DEFAULT_SETTINGS)
  })

  it('falls back per field for a wrong type', () => {
    const odd = join(dir, 'odd.json')
    writeFileSync(
      odd,
      JSON.stringify({ version: 1, checkForUpdates: 'no', reopenLastWorkspace: 0 }),
      'utf-8'
    )
    expect(loadSettings(odd)).toEqual(DEFAULT_SETTINGS)
  })

  it('does not hand out the shared defaults object', () => {
    const loaded = loadSettings(join(dir, 'missing.json'))
    loaded.checkForUpdates = false
    loaded.reopenLastWorkspace = false
    expect(DEFAULT_SETTINGS).toEqual({ checkForUpdates: true, reopenLastWorkspace: true })
  })
})
