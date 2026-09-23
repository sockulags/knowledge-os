// The Referat import window: list Referat's meetings, preview one, choose
// where it goes and which decisions to keep, import it, and report exactly
// which records were created. Everything goes through `window.referat`,
// which the main process answers for this window only.

import '../style.css'
import './referat.css'
import type {
  ExistingRecord,
  ImportContext,
  ImportResultView,
  MeetingPreview,
  MeetingRow,
  NotImportedRecord,
  SkippedRow
} from '../../../shared/referat'

const api = window.referat
const root = document.getElementById('app') as HTMLElement
let context: ImportContext | null = null

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

function show(...nodes: HTMLElement[]): void {
  root.replaceChildren(...nodes)
}

function actions(...buttons: HTMLElement[]): HTMLElement {
  const row = element('div', undefined, 'actions')
  row.append(...buttons)
  return row
}

function recordButton(record: { id: string; title: string }, label = 'Open'): HTMLButtonElement {
  return button(label, () => void api.openRecord(record.id))
}

async function launch(status: HTMLElement): Promise<void> {
  status.textContent = 'Starting Referat…'
  const result = await api.launch()
  status.textContent = result.ok
    ? result.alreadyRunning
      ? 'Referat is already running. Switch to it to record.'
      : 'Referat started. Import the meeting here when Referat has finished the minutes.'
    : result.error
}

function header(title: string, subtitle?: string): HTMLElement[] {
  const nodes: HTMLElement[] = [element('h1', title)]
  if (subtitle !== undefined) nodes.push(element('p', subtitle))
  return nodes
}

function renderUnavailable(kind: 'not-installed' | 'no-data'): void {
  if (kind === 'not-installed') {
    show(
      ...header(
        'Referat is not installed',
        'Referat records meetings and writes their minutes on this computer. Install Referat to record a meeting from here and import its minutes into a project.'
      ),
      actions(button('Close', () => void api.close(), true))
    )
    return
  }
  const status = element('p', undefined, 'status')
  show(
    ...header(
      'No meetings yet',
      'Referat is installed but has not stored any meetings. Record a meeting with Referat, then import it here.'
    ),
    actions(
      button('Record meeting with Referat', () => void launch(status), true),
      button('Close', () => void api.close())
    ),
    status
  )
}

function meetingItem(row: MeetingRow): HTMLElement {
  const item = element('li', undefined, row.importable ? 'meeting' : 'meeting disabled')
  const main = element('div', undefined, 'meeting-main')
  main.append(
    element('strong', row.title),
    element('span', `${row.held} · ${row.duration}`, 'muted')
  )
  const side = element('div', undefined, 'meeting-side')
  side.append(element('span', row.status, row.inProgress ? 'pill amber' : 'pill'))
  item.append(main, side)
  if (row.importable) {
    const open = button('Preview', () => void openPreview(row.id, null))
    side.append(open)
    item.addEventListener('dblclick', () => void openPreview(row.id, null))
  } else if (row.reason !== null) {
    main.append(element('span', row.reason, 'reason'))
  }
  return item
}

function skippedItem(row: SkippedRow): HTMLElement {
  const item = element('li', undefined, 'meeting disabled')
  const main = element('div', undefined, 'meeting-main')
  main.append(element('strong', row.id), element('span', row.error, 'reason'))
  item.append(main)
  return item
}

async function renderList(): Promise<void> {
  show(element('h1', 'Import a meeting from Referat'), element('p', 'Loading meetings…'))
  const result = await api.listMeetings()
  const status = element('p', undefined, 'status')
  const nodes: HTMLElement[] = [
    ...header(
      'Import a meeting from Referat',
      'Choose a finished meeting to import its minutes as a note, with its decisions as drafts.'
    ),
    actions(
      button('Record meeting with Referat', () => void launch(status)),
      button('Refresh', () => void renderList())
    ),
    status
  ]
  if (!result.ok) {
    nodes.push(element('div', result.error, 'error'))
  } else {
    if (result.meetings.length === 0) nodes.push(element('p', 'Referat has no meetings yet.'))
    else {
      const list = element('ul', undefined, 'meetings')
      list.append(...result.meetings.map(meetingItem))
      nodes.push(list)
    }
    if (result.skipped.length > 0) {
      nodes.push(element('h2', 'Could not be read'))
      const list = element('ul', undefined, 'meetings')
      list.append(...result.skipped.map(skippedItem))
      nodes.push(list)
    }
  }
  nodes.push(actions(button('Close', () => void api.close())))
  show(...nodes)
}

function field(label: string, control: HTMLElement, hint?: string): HTMLElement {
  const wrapper = element('label', undefined, 'field')
  wrapper.append(element('span', label, 'field-label'), control)
  if (hint !== undefined) wrapper.append(element('span', hint, 'hint'))
  return wrapper
}

function existingCallout(existing: ExistingRecord[]): HTMLElement {
  const box = element('div', undefined, 'callout')
  box.append(
    element('strong', 'Already imported'),
    element(
      'p',
      'This meeting is already in the knowledge base, so it is not imported again. Open what was imported:'
    )
  )
  const list = element('ul', undefined, 'records')
  for (const record of existing) {
    const item = element('li')
    item.append(
      element('span', record.isDecision ? 'Draft decision' : 'Note', 'kind'),
      element('span', record.title, 'record-title'),
      recordButton(record, 'Open it')
    )
    list.append(item)
  }
  box.append(list)
  return box
}

function foundLine(preview: MeetingPreview): string {
  const parts = [
    preview.found.summary ? 'summary' : null,
    preview.found.decisions ? `decisions (${preview.decisions.length})` : null,
    preview.found.actionItems ? 'action items' : null,
    preview.found.openQuestions ? 'open questions' : null
  ].filter((part) => part !== null)
  return parts.length > 0
    ? `Found in these minutes: ${parts.join(', ')}.`
    : 'No known headings were found; the whole text is imported as the summary.'
}

async function openPreview(meetingId: string, summaryId: string | null): Promise<void> {
  show(element('h1', 'Reading the meeting…'))
  const result = await api.preview(meetingId, summaryId)
  if (!result.ok) {
    show(
      element('h1', 'The meeting could not be read'),
      element('div', result.error, 'error'),
      actions(button('Back to meetings', () => void renderList(), true))
    )
    return
  }
  renderPreview(result.preview)
}

function renderPreview(preview: MeetingPreview): void {
  const back = button('← All meetings', () => void renderList())
  back.className = 'link'
  const nodes: HTMLElement[] = [
    back,
    ...header(preview.title, `${preview.held} · ${preview.duration}`)
  ]

  if (preview.existing.length > 0) {
    nodes.push(existingCallout(preview.existing), actions(button('Close', () => void api.close())))
    show(...nodes)
    return
  }

  const form = element('div', undefined, 'form')

  if (preview.summaries.length > 1) {
    const select = element('select')
    for (const summary of preview.summaries) {
      const option = element('option', summary.label)
      option.value = summary.id
      option.selected = summary.id === preview.summaryId
      select.append(option)
    }
    select.addEventListener('change', () => void openPreview(preview.id, select.value))
    form.append(
      field('Minutes to import', select, 'Referat wrote more than one summary of this meeting.')
    )
  }
  form.append(element('p', foundLine(preview), 'muted'))

  const decisionBoxes: { index: number; input: HTMLInputElement }[] = []
  const decisions = element('fieldset', undefined, 'decisions')
  decisions.append(element('legend', 'Decisions to import as drafts'))
  if (!preview.found.decisions) {
    decisions.append(
      element(
        'p',
        'These minutes have no decisions heading, so no decisions will be imported.',
        'muted'
      )
    )
  } else if (preview.decisions.length === 0) {
    decisions.append(element('p', 'The decisions section lists no decisions.', 'muted'))
  } else {
    decisions.append(
      element(
        'p',
        'Each ticked decision becomes a draft decision linked to the meeting note. Drafts govern nothing until someone accepts them.',
        'muted'
      )
    )
    for (const decision of preview.decisions) {
      const row = element('label', undefined, 'check')
      const input = element('input')
      input.type = 'checkbox'
      input.checked = true
      decisionBoxes.push({ index: decision.index, input })
      const text = element('span')
      text.append(element('span', decision.title, 'decision-title'))
      // Anything nested under the decision in the minutes, below its first line.
      const detail = decision.markdown.split('\n').slice(1).join('\n').trim()
      if (detail !== '') text.append(element('span', detail, 'decision-detail'))
      row.append(input, text)
      decisions.append(row)
    }
  }
  form.append(decisions)

  const projects = context?.projects ?? []
  const project = element('select')
  for (const option of projects) {
    const node = element('option', option.title)
    node.value = option.id
    node.selected = option.id === context?.defaultProjectId
    project.append(node)
  }
  const folder = element('input')
  folder.type = 'text'
  folder.value = context?.defaultFolder ?? ''
  folder.spellcheck = false
  const target = element('div', undefined, 'grid')
  target.append(
    field('Project', project),
    field('Folder', folder, 'Inside the project. Leave empty for its top level.')
  )
  form.append(target)

  const transcript = element('input')
  transcript.type = 'checkbox'
  transcript.checked = false
  transcript.disabled = preview.transcriptSegments === 0
  const transcriptRow = element('label', undefined, 'check')
  transcriptRow.append(
    transcript,
    element(
      'span',
      preview.transcriptSegments === 0
        ? 'Include the full transcript (this meeting has no transcript)'
        : `Include the full transcript (${preview.transcriptSegments} segments). Off by default: the note keeps the minutes only.`
    )
  )
  form.append(transcriptRow)

  const details = element('details')
  details.append(
    element('summary', 'Preview the meeting note'),
    element('pre', preview.noteMarkdown)
  )
  form.append(details)

  const plan = element('p', undefined, 'plan')
  const importButton = button(
    'Import',
    () =>
      void runImport({
        meetingId: preview.id,
        summaryId: preview.summaryId,
        projectId: project.value,
        folder: folder.value,
        includeTranscript: transcript.checked,
        decisions: decisionBoxes.filter((box) => box.input.checked).map((box) => box.index)
      }),
    true
  )
  const updatePlan = (): void => {
    const count = decisionBoxes.filter((box) => box.input.checked).length
    const where = folder.value.trim() === '' ? 'the top level' : folder.value.trim()
    plan.textContent =
      projects.length === 0
        ? 'This knowledge base has no projects yet. Create a project first, then import the meeting.'
        : `Creates the note ${preview.noteId} in ${where}${count > 0 ? ` and ${count} draft decision${count === 1 ? '' : 's'}` : ''}.`
    importButton.disabled = projects.length === 0
  }
  for (const box of decisionBoxes) box.input.addEventListener('change', updatePlan)
  folder.addEventListener('input', updatePlan)
  updatePlan()

  nodes.push(
    form,
    plan,
    actions(
      importButton,
      button('Cancel', () => void renderList())
    )
  )
  show(...nodes)
}

function notImportedList(title: string, records: NotImportedRecord[]): HTMLElement[] {
  if (records.length === 0) return []
  const list = element('ul', undefined, 'records')
  for (const record of records) {
    const item = element('li')
    const text = element('span', undefined, 'record-title')
    text.append(element('strong', record.title), element('span', record.detail, 'reason'))
    item.append(element('span', record.kind === 'note' ? 'Note' : 'Draft decision', 'kind'), text)
    list.append(item)
  }
  return [element('h2', title), list]
}

async function runImport(request: Parameters<typeof api.importMeeting>[0]): Promise<void> {
  show(element('h1', 'Importing…'), element('p', 'Writing the records to the knowledge base.'))
  renderResult(await api.importMeeting(request))
}

async function retry(): Promise<void> {
  show(element('h1', 'Trying again…'))
  renderResult(await api.retryFailed())
}

function renderResult(result: ImportResultView): void {
  if (!result.ok) {
    const nodes: HTMLElement[] = [
      element('h1', 'Nothing was imported'),
      element('div', result.error, 'error')
    ]
    if (result.existing && result.existing.length > 0) nodes.push(existingCallout(result.existing))
    nodes.push(actions(button('Back to meetings', () => void renderList(), true)))
    show(...nodes)
    return
  }
  const problems = result.failed.length + result.notAttempted.length
  const title =
    result.created.length === 0
      ? 'Nothing was imported'
      : problems === 0
        ? 'Imported'
        : 'Imported only in part'
  const nodes: HTMLElement[] = [element('h1', title)]
  if (problems > 0) {
    nodes.push(
      element(
        'div',
        `${result.created.length} of ${result.created.length + problems} records were created. The records listed as created exist in the knowledge base; the others do not.`,
        'error'
      )
    )
  }
  if (result.created.length > 0) {
    const list = element('ul', undefined, 'records')
    for (const record of result.created) {
      const item = element('li')
      const text = element('span', undefined, 'record-title')
      text.append(
        element('strong', record.title),
        element('span', `${record.id} · commit ${record.commit}`, 'muted')
      )
      item.append(
        element('span', record.kind === 'note' ? 'Note' : 'Draft decision', 'kind'),
        text,
        recordButton(record)
      )
      list.append(item)
    }
    nodes.push(element('h2', 'Created'), list)
  }
  nodes.push(...notImportedList('Not created', result.failed))
  nodes.push(...notImportedList('Not attempted', result.notAttempted))
  const buttons: HTMLElement[] = []
  const note = result.created.find((record) => record.kind === 'note')
  if (note) buttons.push(button('Open the note', () => void api.openRecord(note.id), true))
  if (result.canRetry) buttons.push(button('Try the failed decisions again', () => void retry()))
  buttons.push(button('Close', () => void api.close()))
  nodes.push(actions(...buttons))
  show(...nodes)
}

async function start(): Promise<void> {
  show(element('h1', 'Import a meeting from Referat'), element('p', 'Looking for Referat…'))
  try {
    context = await api.context()
  } catch {
    show(
      element('h1', 'Referat could not be checked'),
      element('div', 'Close this window and try again once the knowledge base is open.', 'error'),
      actions(button('Close', () => void api.close(), true))
    )
    return
  }
  if (context.availability.kind !== 'available') {
    renderUnavailable(context.availability.kind)
    return
  }
  await renderList()
}

void start()
