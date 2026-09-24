// Which knowledge base, if any, to open when the app starts. Pure apart from
// the injected file check, so the decision is unit-testable.

import { join } from 'path'
import type { RecentWorkspace } from '../shared/types'

/** The file `kos init` writes and the core requires in a knowledge base's root. */
export const WORKSPACE_MARKER = 'knowledge-os.toml'

export type PathKind = 'directory' | 'file' | 'missing'

export type StartupDecision =
  { kind: 'open'; root: string; reopened: boolean } | { kind: 'start'; notice: string | null }

/** One line for the start page when the last knowledge base cannot be reopened. */
export function notFoundNotice(last: RecentWorkspace): string {
  return `The last knowledge base, ${last.name}, was not found at ${last.root}.`
}

export function notAKnowledgeBaseNotice(last: RecentWorkspace): string {
  return `The last knowledge base, ${last.name}, at ${last.root} is no longer a knowledge base.`
}

/**
 * An explicitly requested folder always wins. Otherwise, with the setting on,
 * reopen the most recent knowledge base when its folder still exists and has
 * the workspace marker; when it does not, say why on the start page. The core
 * still validates the marker's contents when it starts.
 */
export function decideStartup(options: {
  explicit: string | null
  reopenEnabled: boolean
  recent: RecentWorkspace[]
  pathKind: (path: string) => PathKind
}): StartupDecision {
  if (options.explicit) return { kind: 'open', root: options.explicit, reopened: false }
  const last = options.recent[0]
  if (!options.reopenEnabled || last === undefined) return { kind: 'start', notice: null }
  if (options.pathKind(last.root) !== 'directory') {
    return { kind: 'start', notice: notFoundNotice(last) }
  }
  if (options.pathKind(join(last.root, WORKSPACE_MARKER)) !== 'file') {
    return { kind: 'start', notice: notAKnowledgeBaseNotice(last) }
  }
  return { kind: 'open', root: last.root, reopened: true }
}
