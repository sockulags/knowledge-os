// The Clone Knowledge Base window: ask for a Git URL and a folder, run the
// clone with progress and a cancel button, then open the result in the main
// window. Everything goes through `window.kosClone`, which the main process
// answers for this window only. Every string is in shared/cloneText.ts.

import '../style.css'
import './clone.css'
import { mountWindowChrome } from '../../../chrome/windowChrome'
import {
  folderNameFromUrl,
  folderNameProblem,
  gitUrlProblem,
  type CloneProgress
} from '../../../shared/clone'
import { CLONE_TEXT, fill } from '../../../shared/cloneText'

const api = window.kosClone
const root = document.getElementById('app') as HTMLElement

// The window's title bar; this window has no menu.
mountWindowChrome(null)

const form = { url: '', parent: '', name: '', nameEdited: false, showErrors: false }

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

function button(label: string, action: () => void, primary = false): HTMLButtonElement {
  const node = element('button', label, primary ? 'primary' : undefined)
  node.type = 'button'
  node.addEventListener('click', action)
  return node
}

function actions(...buttons: HTMLElement[]): HTMLElement {
  const row = element('div', undefined, 'actions')
  row.append(...buttons)
  return row
}

function joinPath(parent: string, name: string): string {
  const separator = parent.includes('\\') || !parent.includes('/') ? '\\' : '/'
  return parent.replace(/[\\/]+$/, '') + separator + name
}

function heading(): HTMLElement[] {
  return [element('h1', CLONE_TEXT.heading), element('p', CLONE_TEXT.intro)]
}

function field(
  id: string,
  label: string,
  input: HTMLInputElement,
  problem: string | null,
  extra?: HTMLElement
): HTMLElement {
  const wrapper = element('div', undefined, 'field')
  const title = element('label', label, 'field-label')
  title.htmlFor = id
  input.id = id
  input.type = 'text'
  input.spellcheck = false
  input.autocomplete = 'off'
  const row = element('div', undefined, 'field-row')
  row.append(input)
  if (extra) row.append(extra)
  wrapper.append(title, row)
  if (problem !== null) {
    input.setAttribute('aria-invalid', 'true')
    const error = element('p', problem, 'field-error')
    error.id = `${id}-error`
    input.setAttribute('aria-describedby', error.id)
    wrapper.append(error)
  }
  return wrapper
}

function problems(): { url: string | null; name: string | null; parent: string | null } {
  const url = gitUrlProblem(form.url)
  const name = folderNameProblem(form.name)
  return {
    url: url === null ? null : CLONE_TEXT.urlErrors[url],
    name: name === null ? null : CLONE_TEXT.nameErrors[name],
    parent: form.parent.trim() === '' ? CLONE_TEXT.parentEmpty : null
  }
}

function renderForm(focus: 'url' | 'name' | null = 'url'): void {
  const found = problems()
  const shown = form.showErrors ? found : { url: null, name: null, parent: null }

  const url = element('input')
  url.value = form.url
  url.placeholder = CLONE_TEXT.urlPlaceholder
  const parent = element('input')
  parent.value = form.parent
  const name = element('input')
  name.value = form.name
  const hint = element('p', '', 'hint')
  const updateHint = (): void => {
    hint.textContent =
      form.parent.trim() !== '' && form.name.trim() !== ''
        ? fill(CLONE_TEXT.targetHint, { path: joinPath(form.parent.trim(), form.name.trim()) })
        : ''
  }
  updateHint()

  url.addEventListener('input', () => {
    form.url = url.value
    if (!form.nameEdited) {
      form.name = folderNameFromUrl(form.url)
      name.value = form.name
    }
    updateHint()
  })
  parent.addEventListener('input', () => {
    form.parent = parent.value
    updateHint()
  })
  name.addEventListener('input', () => {
    form.name = name.value
    form.nameEdited = form.name !== ''
    updateHint()
  })

  const choose = button(CLONE_TEXT.chooseParent, () => {
    void api.chooseParent(form.parent).then((chosen) => {
      if (chosen === null) return
      form.parent = chosen
      parent.value = chosen
      updateHint()
    })
  })

  const submit = element('button', CLONE_TEXT.clone, 'primary')
  submit.type = 'submit'
  const formNode = element('form', undefined, 'clone-form')
  formNode.noValidate = true
  formNode.append(
    field('clone-url', CLONE_TEXT.urlLabel, url, shown.url),
    field('clone-parent', CLONE_TEXT.parentLabel, parent, shown.parent, choose),
    field('clone-name', CLONE_TEXT.nameLabel, name, shown.name),
    hint,
    actions(
      submit,
      button(CLONE_TEXT.cancel, () => void api.close())
    )
  )
  formNode.addEventListener('submit', (event) => {
    event.preventDefault()
    const now = problems()
    if (now.url !== null || now.name !== null || now.parent !== null) {
      form.showErrors = true
      renderForm(now.url !== null ? 'url' : 'name')
      return
    }
    void run()
  })

  root.replaceChildren(...heading(), formNode)
  if (focus === 'url') url.focus()
  else if (focus === 'name') name.focus()
}

function renderProgress(progress: CloneProgress | null, cancelling: boolean): void {
  const box = element('div', undefined, 'progress')
  box.setAttribute('role', 'status')
  const phase =
    progress === null
      ? CLONE_TEXT.phases.starting
      : cancelling
        ? CLONE_TEXT.cancelling
        : CLONE_TEXT.phases[progress.phase]
  box.append(element('p', phase, 'phase'))
  const bar = element('div', undefined, 'bar')
  const fillBar = element('span')
  if (progress?.phase === 'clone' && progress.percent !== null && !cancelling) {
    fillBar.style.width = `${Math.max(2, Math.min(100, progress.percent))}%`
  } else {
    bar.classList.add('indeterminate')
  }
  bar.append(fillBar)
  box.append(bar)
  if (progress?.line) box.append(element('p', progress.line, 'line'))
  const cancel = button(cancelling ? CLONE_TEXT.cancelling : CLONE_TEXT.cancel, () => {
    cancelRequested = true
    renderProgress(lastProgress, true)
    void api.cancel()
  })
  cancel.disabled = cancelling
  root.replaceChildren(...heading(), box, actions(cancel))
}

function renderError(error: string, detail: string): void {
  const box = element('div', undefined, 'error')
  box.setAttribute('role', 'alert')
  box.append(
    element('h2', CLONE_TEXT.errorTitles[error] ?? CLONE_TEXT.errorTitles.failed),
    element('p', detail)
  )
  root.replaceChildren(
    ...heading(),
    box,
    actions(
      button(
        CLONE_TEXT.tryAgain,
        () => renderForm(error === 'target_not_empty' ? 'name' : 'url'),
        true
      ),
      button(CLONE_TEXT.close, () => void api.close())
    )
  )
}

function renderMessage(text: string): void {
  const notice = element('p', text, 'notice')
  notice.setAttribute('role', 'status')
  root.replaceChildren(
    ...heading(),
    notice,
    actions(
      button(CLONE_TEXT.tryAgain, () => renderForm(), true),
      button(CLONE_TEXT.close, () => void api.close())
    )
  )
}

let lastProgress: CloneProgress | null = null
let cancelRequested = false

async function run(): Promise<void> {
  lastProgress = null
  cancelRequested = false
  renderProgress(null, false)
  const stop = api.onProgress((progress) => {
    lastProgress = progress
    if (!cancelRequested) renderProgress(progress, false)
  })
  const result = await api.start({ url: form.url, parent: form.parent, name: form.name })
  stop()
  if (!result.ok) {
    if (result.error === 'cancelled') renderMessage(CLONE_TEXT.cancelled)
    else renderError(result.error, result.detail)
    return
  }
  if (result.issues.length > 0) {
    const box = element('div', undefined, 'notice')
    box.setAttribute('role', 'status')
    box.append(
      element('h2', CLONE_TEXT.lintTitle),
      element('p', fill(CLONE_TEXT.lintBody, { path: result.root, count: result.issues.length }))
    )
    root.replaceChildren(
      ...heading(),
      box,
      actions(
        button(CLONE_TEXT.openAnyway, () => void api.open(result.root), true),
        button(CLONE_TEXT.close, () => void api.close())
      )
    )
    return
  }
  root.replaceChildren(...heading(), element('p', CLONE_TEXT.opening, 'notice'))
  await api.open(result.root)
}

void api.defaults().then((defaults) => {
  form.parent = defaults.parent
  renderForm()
})
