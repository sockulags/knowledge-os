/** How a folder without its own page shows its name: written as it is on
 * disk, with hyphens and underscores turned into spaces and only the first
 * letter capitalised, so "meeting-notes" reads as "Meeting notes" rather
 * than the raw slug or a CSS-forced "Meeting-Notes". Used everywhere a
 * folder's name (not a page's title) is shown: the tree, the Move dialog,
 * and the "create folder" prompt's place name. */
export function folderDisplayName(name: string): string {
  const spaced = name.replace(/[-_]+/g, " ").trim();
  if (!spaced) return name;
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/** "Skärm bild" -> "skarm-bild": lowercase ASCII words joined by hyphens, the
 * page id rule. It mirrors `knowledge_os.model.kebab` step for step (NFKD,
 * drop every non-ASCII character, lowercase, hyphenate), so a title gives
 * the same id here as in the core; tests/fixtures/kebab_cases.json checks
 * both. `limit` trims the result (`null` keeps all of it), and `fallback` is
 * returned when nothing is left. */
export function kebab(text: string, limit: number | null = 80, fallback = ""): string {
  const folded = text.normalize("NFKD").replace(/[^\x00-\x7f]/g, "");
  let result = folded
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  if (limit !== null) result = result.slice(0, limit).replace(/-+$/, "");
  return result || fallback;
}
