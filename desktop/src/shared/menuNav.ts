// Keyboard movement through the title bar's menus, and the title it shows,
// as pure functions so they are unit-testable apart from the DOM.

import { SHELL_TEXT } from './shellText'

interface Selectable {
  type: string
  enabled: boolean
}

function selectable(item: Selectable): boolean {
  return item.type !== 'separator' && item.enabled
}

/**
 * The next item to focus from `from`, `delta` steps away (1 or -1), skipping
 * separators and disabled items and wrapping around; -1 when none can be
 * focused. `from` -1 starts before the first item (or after the last one).
 */
export function stepIndex(items: Selectable[], from: number, delta: 1 | -1): number {
  const count = items.length
  if (count === 0) return -1
  let index = from < 0 ? (delta === 1 ? -1 : count) : from
  for (let tries = 0; tries < count; tries++) {
    index = (index + delta + count) % count
    if (selectable(items[index])) return index
  }
  return -1
}

export function firstIndex(items: Selectable[]): number {
  return stepIndex(items, -1, 1)
}

export function lastIndex(items: Selectable[]): number {
  return stepIndex(items, -1, -1)
}

/**
 * The item whose label starts with `key` after `from`, wrapping around, as
 * native menus do for a typed letter; -1 when none does.
 */
export function letterIndex(
  items: Array<Selectable & { label: string }>,
  key: string,
  from = -1
): number {
  if (key.length !== 1 || key.trim() === '') return -1
  const letter = key.toLocaleLowerCase()
  const count = items.length
  for (let step = 1; step <= count; step++) {
    const index = (((from + step) % count) + count) % count
    const item = items[index]
    if (selectable(item) && item.label.toLocaleLowerCase().startsWith(letter)) return index
  }
  return -1
}

/**
 * The page title and knowledge base name the title bar shows, from the
 * page's `document.title` ("<page> — <workspace> — Knowledge OS", as the
 * reader writes it). Either part may be empty.
 */
export function titleParts(
  documentTitle: string,
  workspace: string | null
): { page: string; workspace: string } {
  const separator = ' — '
  let rest = documentTitle.trim()
  const app = SHELL_TEXT.appName
  if (rest === app) rest = ''
  else if (rest.endsWith(separator + app)) rest = rest.slice(0, -(separator + app).length)
  const name = workspace?.trim() ?? ''
  if (name !== '') {
    if (rest === name) return { page: '', workspace: name }
    if (rest.endsWith(separator + name)) {
      return { page: rest.slice(0, -(separator + name).length), workspace: name }
    }
    return { page: rest, workspace: name }
  }
  return { page: rest, workspace: '' }
}
