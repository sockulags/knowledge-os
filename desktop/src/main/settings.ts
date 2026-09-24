// App settings, persisted as JSON in Electron's user-data folder next to
// recent-workspaces.json. Only Node built-ins are used so the module is
// unit-testable.

import { mkdirSync, readFileSync, renameSync, writeFileSync } from 'fs'
import { dirname } from 'path'

export interface AppSettings {
  /** Check GitHub for a newer release at startup and every few hours. */
  checkForUpdates: boolean
  /** Open the most recently used knowledge base when the app starts. */
  reopenLastWorkspace: boolean
}

export const DEFAULT_SETTINGS: AppSettings = { checkForUpdates: true, reopenLastWorkspace: true }

/** Read the settings; a missing, damaged, or partial file falls back to the defaults per field. */
export function loadSettings(file: string): AppSettings {
  let parsed: unknown
  try {
    parsed = JSON.parse(readFileSync(file, 'utf-8'))
  } catch {
    return { ...DEFAULT_SETTINGS }
  }
  const stored =
    typeof parsed === 'object' && parsed !== null ? (parsed as Record<string, unknown>) : {}
  const flag = (key: keyof AppSettings): boolean =>
    typeof stored[key] === 'boolean' ? (stored[key] as boolean) : DEFAULT_SETTINGS[key]
  return {
    checkForUpdates: flag('checkForUpdates'),
    reopenLastWorkspace: flag('reopenLastWorkspace')
  }
}

/** Write the settings through a temporary file so a crash never leaves half a file. */
export function saveSettings(file: string, settings: AppSettings): void {
  mkdirSync(dirname(file), { recursive: true })
  const temporary = `${file}.tmp`
  writeFileSync(temporary, JSON.stringify({ version: 1, ...settings }, null, 2), 'utf-8')
  renameSync(temporary, file)
}
