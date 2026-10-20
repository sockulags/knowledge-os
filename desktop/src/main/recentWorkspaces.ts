// The recently opened workspaces, persisted as JSON in Electron's user-data
// folder. Only Node built-ins are used so the module is unit-testable.

import { readFileSync } from 'fs'
import type { RecentEntry, RecentWorkspace } from '../shared/types'
import { writeFileAtomic } from './atomicFile'
import type { PathKind } from './reopen'

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

/** Drop the entry for the folder `root`, if the list has one. */
export function removeRecent(
  list: RecentWorkspace[],
  root: string,
  platform: NodeJS.Platform = process.platform
): RecentWorkspace[] {
  return list.filter((item) => !sameRoot(item.root, root, platform))
}

/** The list as the start page shows it: a folder that is no longer there is marked missing. */
export function markMissing(
  list: RecentWorkspace[],
  pathKind: (path: string) => PathKind
): RecentEntry[] {
  return list.map((item) => ({ ...item, missing: pathKind(item.root) !== 'directory' }))
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
  writeFileAtomic(file, JSON.stringify({ version: 1, workspaces: list }, null, 2))
}
