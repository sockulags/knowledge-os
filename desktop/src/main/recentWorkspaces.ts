// The recently opened workspaces, persisted as JSON in Electron's user-data
// folder. Only Node built-ins are used so the module is unit-testable.

import { mkdirSync, readFileSync, renameSync, writeFileSync } from 'fs'
import { dirname } from 'path'
import type { RecentWorkspace } from '../shared/types'

export const MAX_RECENT = 10

function sameRoot(a: string, b: string, platform: NodeJS.Platform): boolean {
  const normalize = (value: string): string => {
    const trimmed = value.replace(/[\\/]+$/, '')
    return platform === 'win32' ? trimmed.replace(/\//g, '\\').toLowerCase() : trimmed
  }
  return normalize(a) === normalize(b)
}

/** Put `entry` first, drop any older entry for the same folder, and cap the list. */
export function addRecent(
  list: RecentWorkspace[],
  entry: RecentWorkspace,
  platform: NodeJS.Platform = process.platform
): RecentWorkspace[] {
  const rest = list.filter((item) => !sameRoot(item.root, entry.root, platform))
  return [entry, ...rest].slice(0, MAX_RECENT)
}

function isRecentWorkspace(value: unknown): value is RecentWorkspace {
  if (typeof value !== 'object' || value === null) return false
  const item = value as Record<string, unknown>
  return (
    typeof item['root'] === 'string' &&
    item['root'] !== '' &&
    typeof item['name'] === 'string' &&
    typeof item['lastOpened'] === 'string'
  )
}

/** Read the list; a missing or damaged file yields an empty list instead of an error. */
export function loadRecent(file: string): RecentWorkspace[] {
  let parsed: unknown
  try {
    parsed = JSON.parse(readFileSync(file, 'utf-8'))
  } catch {
    return []
  }
  const items = (parsed as { workspaces?: unknown })?.workspaces
  if (!Array.isArray(items)) return []
  return items.filter(isRecentWorkspace).slice(0, MAX_RECENT)
}

/** Write the list through a temporary file so a crash never leaves half a file. */
export function saveRecent(file: string, list: RecentWorkspace[]): void {
  mkdirSync(dirname(file), { recursive: true })
  const temporary = `${file}.tmp`
  writeFileSync(temporary, JSON.stringify({ version: 1, workspaces: list }, null, 2), 'utf-8')
  renameSync(temporary, file)
}
