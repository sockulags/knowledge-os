// Record ids for imported meetings: readable, stable for the same meeting,
// and never reused. Ids follow the core's rule, lowercase words joined by
// hyphens (`knowledge_os/model.py` ID_PATTERN).

export const RECORD_ID_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/

/** Letters that Unicode decomposition does not reduce to ASCII. */
const TRANSLITERATION: Record<string, string> = {
  æ: 'ae',
  ø: 'o',
  œ: 'oe',
  ß: 'ss',
  ł: 'l',
  đ: 'd',
  ð: 'd',
  þ: 'th'
}

/** Lowercase ASCII words joined by hyphens, at most `maxLength` characters, cut at a word boundary. */
export function slugify(text: string, maxLength = 50): string {
  const ascii = text
    .toLowerCase()
    .replace(/[æøœßłđðþ]/g, (letter) => TRANSLITERATION[letter] ?? letter)
    .normalize('NFKD')
    .replace(/\p{M}/gu, '')
  const slug = ascii.replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')
  if (slug.length <= maxLength) return slug
  const cut = slug.slice(0, maxLength + 1)
  const boundary = cut.lastIndexOf('-')
  return (boundary > 0 ? cut.slice(0, boundary) : slug.slice(0, maxLength)).replace(/-+$/, '')
}

function pad(value: number): string {
  return String(value).padStart(2, '0')
}

/** The calendar date of an ISO timestamp on this computer's clock, as YYYY-MM-DD. */
export function localDate(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso.slice(0, 10)
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

/** `2026-09-20-weekly-sync` for a meeting titled "Weekly sync" held on 20 September 2026. */
export function noteBaseId(date: string, title: string): string {
  return `${date}-${slugify(title) || 'meeting'}`
}

/** `2026-09-20-use-postgres-for-storage` for a decision taken on that day. */
export function decisionBaseId(date: string, text: string): string {
  return `${date}-${slugify(text) || 'decision'}`
}

/** `base` when free, otherwise `base-2`, `base-3`, ...: an existing id is never reused. */
export function uniqueId(base: string, taken: ReadonlySet<string>): string {
  if (!taken.has(base)) return base
  for (let n = 2; ; n++) {
    const candidate = `${base}-${n}`
    if (!taken.has(candidate)) return candidate
  }
}

/** Whether `id` is `base` or one of its suffixed forms. */
export function isSuffixedForm(id: string, base: string): boolean {
  return id === base || (id.startsWith(`${base}-`) && /^\d+$/.test(id.slice(base.length + 1)))
}

const SAFE_FOLDER_SEGMENT = /^[\p{L}\p{N}][\p{L}\p{N} ._-]*$/u

/** A folder inside a project as the write API expects it, or null when it is not a safe relative path. */
export function cleanFolder(value: string): string | null {
  const segments = value
    .trim()
    .replace(/\\/g, '/')
    .split('/')
    .map((segment) => segment.trim())
    .filter((segment) => segment !== '')
  if (segments.some((segment) => !SAFE_FOLDER_SEGMENT.test(segment) || segment.endsWith('.'))) {
    return null
  }
  return segments.join('/')
}
