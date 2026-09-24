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
