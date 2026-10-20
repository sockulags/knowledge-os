// The start page: open, create, or reopen a knowledge base, and show why the
// Python core could not start. Once a workspace is open, the main process
// replaces this page with the reader UI.

import './style.css'
import mark from '../../../build/icon.svg'
import { CLONE_TEXT } from '../../shared/cloneText'
import type { ErrorKind, RecentEntry, ShellState } from '../../shared/types'
import { actions, button, element } from './dom'

const api = window.kosDesktop
const root = document.getElementById('app') as HTMLElement

const ERROR_TITLES: Record<ErrorKind, string> = {
  'python-missing': 'Python is not available',
  'core-missing': 'The Knowledge OS core is missing',
  'invalid-workspace': 'Not a valid knowledge base',
  'early-exit': 'The Python core stopped',
  'create-failed': 'The knowledge base was not created'
}

/** The app's mark beside its name, at the top of the start page. */
function brand(): HTMLElement {
  const wrapper = element('div', undefined, 'brand')
  const image = element('img')
  image.src = mark
  image.alt = ''
  wrapper.append(image, element('h1', 'Knowledge OS'))
  return wrapper
}

function mainActions(): HTMLElement {
  return actions(
    button('Open knowledge base…', api.openWorkspace, true),
    button('Create new knowledge base…', api.createWorkspace),
    button(CLONE_TEXT.startButton, api.cloneWorkspace)
  )
}

/** One of the three ways to start, with a sentence on when to pick it. */
interface Choice {
  label: string
  description: string
  shortcut?: string
  action: () => Promise<void>
}

const CHOICES: Choice[] = [
  {
    label: 'Open knowledge base…',
    description:
      'Pick a folder that already is a knowledge base, such as one you created ' +
      'earlier or copied from another computer.',
    shortcut: 'Ctrl+O',
    action: api.openWorkspace
  },
  {
    label: 'Create new knowledge base…',
    description:
      'Start from nothing: choose an empty folder and Knowledge OS sets it up, ' +
      'ready for your first notes.',
    shortcut: 'Ctrl+N',
    action: api.createWorkspace
  },
  {
    label: CLONE_TEXT.startButton,
    description:
      'Copy a knowledge base that lives in a Git repository, such as one on GitHub, ' +
      'to this computer and open it.',
    action: api.cloneWorkspace
  }
]

/**
 * The first-run version of the actions: each choice with what it does, so
 * someone who has never opened a knowledge base knows which one to pick.
 */
function choiceList(): HTMLElement[] {
  const list = element('ul', undefined, 'choices')
  CHOICES.forEach((choice, index) => {
    const title = element('span', choice.label, 'title')
    if (choice.shortcut !== undefined) title.append(element('kbd', choice.shortcut))
    const entry = button('', choice.action, index === 0)
    entry.replaceChildren(title, element('span', choice.description, 'description'))
    const row = element('li')
    row.append(entry)
    list.append(row)
  })
  return [element('h2', 'Get started'), list]
}

/**
 * The recent knowledge bases. A folder that is gone is marked "Folder not
 * found"; every entry has its own Remove button, after the entry in tab order.
 */
function recentList(recent: RecentEntry[]): HTMLElement[] {
  if (recent.length === 0) return []
  const list = element('ul', undefined, 'recent')
  for (const item of recent) {
    const entry = button('', () => api.openRecent(item.root), false)
    entry.className = 'open'
    const title = element('span', item.name, 'title')
    if (item.missing) title.append(element('span', 'Folder not found', 'badge'))
    entry.append(title, element('span', item.root, 'path'))
    const remove = button('×', () => api.removeRecent(item.root))
    remove.className = 'remove'
    remove.title = 'Remove from list'
    remove.setAttribute('aria-label', `Remove ${item.name} from the recent list`)
    const row = element('li', undefined, item.missing ? 'missing' : undefined)
    row.append(entry, remove)
    list.append(row)
  }
  return [element('h2', 'Recent'), list]
}

function render(state: ShellState): void {
  const nodes: HTMLElement[] = []
  switch (state.kind) {
    case 'start': {
      const firstRun = state.recent.length === 0
      nodes.push(
        brand(),
        element(
          'p',
          firstRun
            ? 'A knowledge base is a folder of Markdown files on this computer. ' +
                'Knowledge OS reads and indexes the folder so you can browse, search, ' +
                'and follow links between your notes; the files stay plain text that ' +
                'any editor can open.'
            : 'Open a knowledge base folder, create a new, empty one, or clone one from a Git repository.'
        )
      )
      if (state.notice) {
        const notice = element('p', state.notice, 'notice')
        notice.setAttribute('role', 'status')
        nodes.push(notice)
      }
      if (firstRun) nodes.push(...choiceList())
      else nodes.push(mainActions(), ...recentList(state.recent))
      break
    }
    case 'starting':
      nodes.push(element('h1', 'Opening knowledge base…'), element('p', state.root, 'path'))
      break
    case 'creating':
      nodes.push(element('h1', 'Creating knowledge base…'), element('p', state.root, 'path'))
      break
    case 'ready':
      nodes.push(element('h1', 'Loading…'))
      break
    case 'error': {
      nodes.push(element('h1', ERROR_TITLES[state.error]))
      if (state.root !== null) nodes.push(element('p', state.root, 'path'))
      nodes.push(element('div', state.message, 'error'))
      if (state.detail !== '') nodes.push(element('pre', state.detail))
      nodes.push(
        actions(
          button('Try again', api.retry, true),
          button('Open another knowledge base…', api.openWorkspace),
          button('Back to start', api.showStart)
        )
      )
      break
    }
  }
  root.replaceChildren(...nodes)
}

api.onStateChanged(render)
void api.getState().then(render)
