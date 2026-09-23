// Splits a Referat summary (Markdown) into the sections the import maps to
// records: summary, decisions, action items, and open questions. Referat
// stores minutes only as Markdown written by a language model from a prompt
// template, so the parser matches headings by name at any level, in Swedish
// (the default "protokoll" template) and English, and keeps everything it
// does not recognise.

export type SectionKind = 'summary' | 'decisions' | 'actionItems' | 'openQuestions'

export const SECTION_KINDS: readonly SectionKind[] = [
  'summary',
  'decisions',
  'actionItems',
  'openQuestions'
]

const ALIASES: Record<SectionKind, readonly string[]> = {
  summary: ['sammanfattning', 'sammandrag', 'översikt', 'summary', 'overview'],
  decisions: [
    'beslut',
    'fattade beslut',
    'beslutslogg',
    'decisions',
    'decision',
    'decisions made',
    'key decisions',
    'decision log'
  ],
  actionItems: [
    'actionpunkter',
    'åtgärdspunkter',
    'åtgärder',
    'att göra',
    'nästa steg',
    'action items',
    'action points',
    'actions',
    'next steps',
    'to do',
    'todo',
    'to-dos'
  ],
  openQuestions: [
    'öppna frågor',
    'olösta frågor',
    'frågor',
    'open questions',
    'unresolved questions',
    'outstanding questions',
    'questions'
  ]
}

/** A section the parser did not recognise, kept with its own heading text. */
export interface OtherSection {
  heading: string
  content: string
}

export interface ParsedSummary {
  /** Recognised sections; several sections of one kind are joined. Content has no heading line. */
  sections: Partial<Record<SectionKind, string>>
  /** Text before the first heading (a leading title heading is dropped). */
  preamble: string
  other: OtherSection[]
}

const ATX_HEADING = /^ {0,3}(#{1,6})(?:[ \t]+(.*?))?[ \t]*#*[ \t]*$/
/** A line that is only bold text, which models often use as a heading: `**Beslut:**`. */
const BOLD_HEADING = /^ {0,3}(?:\*\*|__)(.+?)(?:\*\*|__)[ \t]*:?[ \t]*$/
const FENCE = /^ {0,3}(`{3,}|~{3,})/
/** Bold-line headings are the deepest level, so they never end a real heading's section. */
const BOLD_LEVEL = 7

/** Heading text reduced to a comparable key: no emphasis, numbering, emoji, colon, or case. */
export function normalizeHeading(text: string): string {
  return text
    .replace(/[*_`]/g, '')
    .replace(/\([^)]*\)\s*$/, '')
    .replace(/^[^\p{L}\p{N}]+/u, '')
    .replace(/^\d+[.)]?\s+/, '')
    .replace(/[\s:.]+$/, '')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase()
}

export function sectionKind(heading: string): SectionKind | null {
  const key = normalizeHeading(heading)
  for (const kind of SECTION_KINDS) {
    if (ALIASES[kind].includes(key)) return kind
  }
  return null
}

interface Heading {
  line: number
  level: number
  text: string
  kind: SectionKind | null
}

function findHeadings(lines: string[]): Heading[] {
  const headings: Heading[] = []
  let fence: string | null = null
  lines.forEach((line, index) => {
    const fenceMatch = FENCE.exec(line)
    if (fenceMatch) {
      const marker = fenceMatch[1][0]
      if (fence === null) fence = marker
      else if (fence === marker) fence = null
      return
    }
    if (fence !== null) return
    const atx = ATX_HEADING.exec(line)
    if (atx) {
      const text = (atx[2] ?? '').trim()
      headings.push({ line: index, level: atx[1].length, text, kind: sectionKind(text) })
      return
    }
    const bold = BOLD_HEADING.exec(line)
    if (bold) {
      const kind = sectionKind(bold[1])
      // Only a recognised name makes a bold line a heading; other bold lines are prose.
      if (kind !== null) headings.push({ line: index, level: BOLD_LEVEL, text: bold[1], kind })
    }
  })
  return headings
}

function trimBlankLines(lines: string[]): string {
  let start = 0
  let end = lines.length
  while (start < end && lines[start].trim() === '') start++
  while (end > start && lines[end - 1].trim() === '') end--
  return lines.slice(start, end).join('\n')
}

/**
 * Splits summary Markdown into recognised sections. A recognised heading owns
 * everything up to the next heading at the same or a higher level, or the
 * next recognised heading at any level, so sub-headings inside "Beslut"
 * belong to the decisions.
 */
export function parseSummary(markdown: string): ParsedSummary {
  const lines = markdown.replace(/\r\n?/g, '\n').split('\n')
  const headings = findHeadings(lines)
  const sections: Partial<Record<SectionKind, string>> = {}
  const other: OtherSection[] = []

  const firstLine = headings.length > 0 ? headings[0].line : lines.length
  const preamble = trimBlankLines(lines.slice(0, firstLine))

  let i = 0
  while (i < headings.length) {
    const heading = headings[i]
    let j = i + 1
    if (heading.kind !== null) {
      while (
        j < headings.length &&
        headings[j].kind === null &&
        headings[j].level > heading.level
      ) {
        j++
      }
    }
    const end = j < headings.length ? headings[j].line : lines.length
    const content = trimBlankLines(lines.slice(heading.line + 1, end))
    if (heading.kind !== null) {
      const previous = sections[heading.kind]
      sections[heading.kind] =
        previous === undefined || previous === '' ? content : `${previous}\n\n${content}`
    } else if (!(i === 0 && heading.level === 1 && content === '')) {
      // A leading level-1 heading with nothing under it is the document title.
      if (content !== '' || heading.text !== '') other.push({ heading: heading.text, content })
    }
    i = j
  }
  return { sections, preamble, other }
}

/** One item of a list-shaped section: its first line and anything nested under it. */
export interface SectionItem {
  text: string
  detail: string
}

const LIST_ITEM = /^(\s*)(?:[-*+•]|\d+[.)])\s+(.*)$/
const TASK_BOX = /^\[[ xX]\]\s+/
/** Placeholder text a model writes when a section is empty: "Inga beslut fattades.", "None." */
const NONE_MARKER =
  /^(?:inga(?: beslut| frågor| actionpunkter| åtgärder)?|inget(?: beslut)?|no(?: decisions?| action items| open questions| questions)?|none|n\/a|-|–|—)(?:\s+(?:fattades|togs|noterades|was made|were made|made|recorded))?[.!]?$/i

function isNoneMarker(text: string): boolean {
  return NONE_MARKER.test(text.replace(/[*_]/g, '').trim())
}

function indentOf(line: string): number {
  const match = /^[ \t]*/.exec(line)
  return match ? match[0].replace(/\t/g, '    ').length : 0
}

function dedent(lines: string[]): string {
  const nonBlank = lines.filter((line) => line.trim() !== '')
  if (nonBlank.length === 0) return ''
  const indent = Math.min(...nonBlank.map(indentOf))
  return trimBlankLines(lines.map((line) => line.replace(/\t/g, '    ').slice(indent)))
}

function listItems(lines: string[]): SectionItem[] {
  const itemLines = lines.filter((line) => LIST_ITEM.test(line))
  if (itemLines.length === 0) return []
  const topIndent = Math.min(...itemLines.map(indentOf))
  const items: { text: string; rest: string[] }[] = []
  for (const line of lines) {
    const match = LIST_ITEM.exec(line)
    if (match && indentOf(line) === topIndent) {
      items.push({ text: match[2].replace(TASK_BOX, '').trim(), rest: [] })
    } else if (items.length > 0) {
      items[items.length - 1].rest.push(line)
    }
  }
  return items.map((item) => ({ text: item.text, detail: dedent(item.rest) }))
}

function headingItems(lines: string[]): SectionItem[] {
  const headings = findHeadings(lines)
  if (headings.length === 0) return []
  return headings.map((heading, index) => {
    const end = index + 1 < headings.length ? headings[index + 1].line : lines.length
    return { text: heading.text, detail: trimBlankLines(lines.slice(heading.line + 1, end)) }
  })
}

function paragraphItems(lines: string[]): SectionItem[] {
  const items: SectionItem[] = []
  let current: string[] = []
  const flush = (): void => {
    if (current.length > 0) {
      items.push({ text: current[0].trim(), detail: dedent(current.slice(1)) })
      current = []
    }
  }
  for (const line of lines) {
    if (line.trim() === '') flush()
    else current.push(line)
  }
  flush()
  return items
}

/**
 * The items of one section: top-level list items with their nested lines,
 * else one item per sub-heading, else one per paragraph. Placeholders such as
 * "Inga beslut fattades." yield no items.
 */
export function sectionItems(content: string): SectionItem[] {
  const lines = content.replace(/\r\n?/g, '\n').split('\n')
  let items = listItems(lines)
  if (items.length === 0) items = headingItems(lines)
  if (items.length === 0) items = paragraphItems(lines)
  return items.filter((item) => item.text !== '' && !isNoneMarker(item.text))
}

/** Markdown reduced to plain text for a title: no emphasis, code marks, or link targets. */
export function plainText(markdown: string): string {
  return markdown
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/[*_`~]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
}

/** Pushes every heading in `content` down to at least `minLevel`, so it nests under the note's own sections. */
export function demoteHeadings(content: string, minLevel: number): string {
  let fence: string | null = null
  return content
    .split('\n')
    .map((line) => {
      const fenceMatch = FENCE.exec(line)
      if (fenceMatch) {
        const marker = fenceMatch[1][0]
        if (fence === null) fence = marker
        else if (fence === marker) fence = null
        return line
      }
      if (fence !== null) return line
      const atx = /^ {0,3}(#{1,6})(?=[ \t]|$)/.exec(line)
      if (!atx || atx[1].length >= minLevel) return line
      return '#'.repeat(minLevel) + line.slice(atx[0].length)
    })
    .join('\n')
}
