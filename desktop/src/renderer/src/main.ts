// The start page: open, create, or reopen a knowledge base, and show why the
// Python core could not start. Once a workspace is open, the main process
// replaces this page with the reader UI.

import './style.css'
import type { ErrorKind, RecentWorkspace, ShellState } from '../../shared/types'

const api = window.kosDesktop
const root = document.getElementById('app') as HTMLElement

const ERROR_TITLES: Record<ErrorKind, string> = {
  'python-missing': 'Python is not available',
  'core-missing': 'The Knowledge OS core is missing',
  'invalid-workspace': 'Not a valid knowledge base',
  'early-exit': 'The Python core stopped',
  'create-failed': 'The knowledge base was not created'
}

function element<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  text?: string,
  className?: string
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag)
  if (text !== undefined) node.textContent = text
  if (className !== undefined) node.className = className
  return node
}

function button(label: string, action: () => Promise<void>, primary = false): HTMLButtonElement {
  const node = element('button', label, primary ? 'primary' : undefined)
  node.type = 'button'
  node.addEventListener('click', () => {
    void action()
  })
  return node
}

function mainActions(): HTMLElement {
  const actions = element('div', undefined, 'actions')
  actions.append(
    button('Open knowledge base…', api.openWorkspace, true),
    button('Create new knowledge base…', api.createWorkspace)
  )
  return actions
}

function recentList(recent: RecentWorkspace[]): HTMLElement[] {
  if (recent.length === 0) return []
  const list = element('ul', undefined, 'recent')
  for (const item of recent) {
    const entry = button(item.name, () => api.openRecent(item.root))
    entry.append(element('span', item.root, 'path'))
    const row = element('li')
    row.append(entry)
    list.append(row)
  }
  return [element('h2', 'Recent'), list]
}

function render(state: ShellState): void {
  const nodes: HTMLElement[] = []
  switch (state.kind) {
    case 'start':
      nodes.push(
        element('h1', 'Knowledge OS'),
        element('p', 'Open a knowledge base folder or create a new, empty one.'),
        mainActions(),
        ...recentList(state.recent)
      )
      break
    case 'starting':
      nodes.push(element('h1', 'Opening knowledge base…'), element('p', state.root, 'path'))
      break
    case 'ready':
      nodes.push(element('h1', 'Loading…'))
      break
    case 'error': {
      nodes.push(element('h1', ERROR_TITLES[state.error]))
      if (state.root !== null) nodes.push(element('p', state.root, 'path'))
      nodes.push(element('div', state.message, 'error'))
      if (state.detail !== '') nodes.push(element('pre', state.detail))
      const actions = element('div', undefined, 'actions')
      actions.append(
        button('Try again', api.retry, true),
        button('Open another knowledge base…', api.openWorkspace),
        button('Back to start', api.showStart)
      )
      nodes.push(actions)
      break
    }
  }
  root.replaceChildren(...nodes)
}

api.onStateChanged(render)
void api.getState().then(render)
