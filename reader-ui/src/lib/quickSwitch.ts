// Pure ranking and grouping for the Ctrl K / Cmd K quick switcher. No React
// and no DOM here, so `npm test` can run it under Node's own test runner.
// Every word shown to the reader comes from the API (`kind_label`, the
// group headings in `language.quick_find_groups`); this module only orders.

import type { RecordIndexEntry, SearchResult } from "../api/types";

/** Group order when two groups' best matches rank the same. */
export const GROUP_ORDER = ["projects", "decisions", "pages", "skills", "docs"];

/** Rows shown per title group, and for pages found only in their text. */
export const TITLE_LIMIT_PER_GROUP = 5;
export const TEXT_LIMIT = 6;

/** Lowercase and drop accents, so "mote" finds "Möte" and "cafe" finds "Café". */
export function normalize(text: string): string {
  return text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

function words(text: string): string[] {
  return text.split(/[^\p{L}\p{N}]+/u).filter(Boolean);
}

/**
 * How well `title` matches `query`, or 0 for no match. Highest first: the
 * exact title, the title's start, the start of any word, anywhere in the
 * title; then every typed word found in the title in any order, where a
 * word matching the start of a title word counts double.
 */
export function scoreTitle(title: string, query: string): number {
  const q = normalize(query).trim().replace(/\s+/g, " ");
  if (!q) return 0;
  const t = normalize(title);
  if (t === q) return 1000;
  if (t.startsWith(q)) return 800;
  const titleWords = words(t);
  if (!q.includes(" ") && titleWords.some((word) => word.startsWith(q))) return 600;
  if (t.includes(q)) return 400;
  let points = 0;
  for (const token of q.split(" ")) {
    if (titleWords.some((word) => word.startsWith(token))) points += 2;
    else if (t.includes(token)) points += 1;
    else return 0;
  }
  return 100 + points;
}

export interface Ranked {
  entry: RecordIndexEntry;
  score: number;
}

/** Every matching entry, best first; ties go to the shorter, then alphabetically first, title. */
export function rankTitles(entries: RecordIndexEntry[], query: string): Ranked[] {
  const ranked: Ranked[] = [];
  for (const entry of entries) {
    const score = scoreTitle(entry.title, query);
    if (score > 0) ranked.push({ entry, score });
  }
  return ranked.sort(
    (a, b) =>
      b.score - a.score || a.entry.title.length - b.entry.title.length || a.entry.title.localeCompare(b.entry.title),
  );
}

/** Where an entry opens in the reader. */
export function hrefFor(entry: Pick<RecordIndexEntry, "id" | "kind" | "group">): string {
  if (entry.group === "projects") return `/p/${entry.id}`;
  if (entry.kind === "skill") return `/s/${entry.id}`;
  if (entry.kind === "doc") return `/f/${entry.id}`;
  return `/r/${entry.id}`;
}

export interface SwitchOption {
  /** Unique across the whole list; also the basis of the option's DOM id. */
  key: string;
  entry: RecordIndexEntry;
  href: string;
  /** The full-text snippet (trusted HTML from the API), for text-only hits. */
  snippetHtml: string | null;
}

export interface SwitchSection {
  /** A key of `language.quick_find_groups`; `text` for pages found by their body. */
  group: string;
  options: SwitchOption[];
}

function groupRank(group: string): number {
  const index = GROUP_ORDER.indexOf(group);
  return index === -1 ? GROUP_ORDER.length : index;
}

/**
 * The switcher's sections for `query`: title matches grouped by kind, groups
 * ordered by their best match, then pages found only by a word in their text
 * (full-text hits already listed under a title group are left out). Each
 * option's position in the flattened list is its keyboard index.
 */
export function buildSections(
  entries: RecordIndexEntry[],
  query: string,
  textHits: SearchResult[] | null,
): SwitchSection[] {
  const ranked = rankTitles(entries, query);
  const byGroup = new Map<string, Ranked[]>();
  for (const item of ranked) {
    const group = GROUP_ORDER.includes(item.entry.group) ? item.entry.group : "pages";
    const list = byGroup.get(group) ?? [];
    if (list.length < TITLE_LIMIT_PER_GROUP) list.push(item);
    byGroup.set(group, list);
  }
  const sections: SwitchSection[] = [...byGroup.entries()]
    .sort(([groupA, a], [groupB, b]) => b[0].score - a[0].score || groupRank(groupA) - groupRank(groupB))
    .map(([group, items]) => ({
      group,
      options: items.map(({ entry }) => ({
        key: `${group}:${entry.kind}:${entry.id}`,
        entry,
        href: hrefFor(entry),
        snippetHtml: null,
      })),
    }));

  if (textHits && textHits.length > 0) {
    const shown = new Set(sections.flatMap((section) => section.options.map((option) => option.entry.id)));
    const indexById = new Map(entries.filter((entry) => entry.kind !== "skill" && entry.kind !== "doc").map((entry) => [entry.id, entry]));
    const options: SwitchOption[] = [];
    for (const hit of textHits) {
      if (shown.has(hit.id) || options.length >= TEXT_LIMIT) continue;
      shown.add(hit.id);
      const entry: RecordIndexEntry = indexById.get(hit.id) ?? {
        id: hit.id,
        title: hit.title,
        kind: hit.record_kind === "decision" ? "decision" : hit.type,
        status_pill: null,
        project: hit.project_id,
        group: hit.record_kind === "decision" ? "decisions" : "pages",
        kind_label: hit.record_kind_label || hit.type_label,
      };
      options.push({ key: `text:${hit.id}`, entry, href: hrefFor(entry), snippetHtml: hit.snippet_html });
    }
    if (options.length > 0) sections.push({ group: "text", options });
  }
  return sections;
}

/** Ctrl K everywhere, Cmd K on macOS (where Ctrl K is a text-editing key). */
export function isQuickSwitchShortcut(
  event: Pick<KeyboardEvent, "key" | "ctrlKey" | "metaKey" | "altKey" | "shiftKey">,
  mac: boolean,
): boolean {
  if (event.key.toLowerCase() !== "k" || event.altKey || event.shiftKey) return false;
  return mac ? event.metaKey && !event.ctrlKey : event.ctrlKey && !event.metaKey;
}

export function isMacPlatform(platform: string): boolean {
  return /Mac|iPhone|iPad|iPod/.test(platform);
}

/** Whether this browser runs on macOS (or iOS), where the shortcut is Cmd K. */
export const MAC = typeof navigator !== "undefined" && isMacPlatform(navigator.platform ?? "");

/** The shortcut as printed on the key caps. */
export const SHORTCUT_KEYS = MAC ? "⌘ K" : "Ctrl K";
