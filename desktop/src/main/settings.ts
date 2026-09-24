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
  /**
   * The reader's sidebar width in pixels, or null for its default. Kept here
   * because the reader runs on a new local port each launch, and browser
   * storage, kept per origin, would forget it on every restart.
   */
  readerSidebarWidth: number | null
}

export const DEFAULT_SETTINGS: AppSettings = {
  checkForUpdates: true,
  reopenLastWorkspace: true,
  readerSidebarWidth: null
}

/** A plausible sidebar width, or null. The reader applies its own limits. */
export function sidebarWidth(value: unknown): number | null {
  if (typeof value !== 'number' || !Number.isFinite(value)) return null
  if (value < 100 || value > 2000) return null
  return Math.round(value)
}

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
  const flag = (key: 'checkForUpdates' | 'reopenLastWorkspace'): boolean =>
    typeof stored[key] === 'boolean' ? (stored[key] as boolean) : DEFAULT_SETTINGS[key]
  return {
    checkForUpdates: flag('checkForUpdates'),
    reopenLastWorkspace: flag('reopenLastWorkspace'),
    readerSidebarWidth: sidebarWidth(stored['readerSidebarWidth'])
  }
}

/** Write the settings through a temporary file so a crash never leaves half a file. */
export function saveSettings(file: string, settings: AppSettings): void {
  mkdirSync(dirname(file), { recursive: true })
  const temporary = `${file}.tmp`
  writeFileSync(temporary, JSON.stringify({ version: 1, ...settings }, null, 2), 'utf-8')
  renameSync(temporary, file)
}
