/** One line of a two-sided comparison: in both texts, only in the older
 * ("removed"), or only in the newer ("added"). */
export interface DiffLine {
  kind: "equal" | "removed" | "added";
  text: string;
}

/** Above this many line pairs the middle of the texts is shown as removed
 * then added instead of being matched, so a huge page cannot stall the tab. */
const MAX_CELLS = 4_000_000;

/** A line-by-line diff from `older` to `newer` (longest common subsequence),
 * used to show a write conflict: the version on disk against the text being
 * edited. Lines shared at the start and end are matched first. */
export function lineDiff(older: string, newer: string): DiffLine[] {
  const a = older.split("\n");
  const b = newer.split("\n");
  let start = 0;
  while (start < a.length && start < b.length && a[start] === b[start]) start++;
  let endA = a.length;
  let endB = b.length;
  while (endA > start && endB > start && a[endA - 1] === b[endB - 1]) {
    endA--;
    endB--;
  }

  const head: DiffLine[] = a.slice(0, start).map((text) => ({ kind: "equal", text }));
  const tail: DiffLine[] = a.slice(endA).map((text) => ({ kind: "equal", text }));
  const midA = a.slice(start, endA);
  const midB = b.slice(start, endB);
  return [...head, ...middle(midA, midB), ...tail];
}

function middle(a: string[], b: string[]): DiffLine[] {
  if (a.length * b.length > MAX_CELLS) {
    return [
      ...a.map((text): DiffLine => ({ kind: "removed", text })),
      ...b.map((text): DiffLine => ({ kind: "added", text })),
    ];
  }
  // lengths[i][j]: the longest common subsequence of a[i:] and b[j:].
  const width = b.length + 1;
  const lengths = new Uint32Array((a.length + 1) * width);
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      lengths[i * width + j] =
        a[i] === b[j]
          ? lengths[(i + 1) * width + j + 1] + 1
          : Math.max(lengths[(i + 1) * width + j], lengths[i * width + j + 1]);
    }
  }
  const lines: DiffLine[] = [];
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      lines.push({ kind: "equal", text: a[i] });
      i++;
      j++;
    } else if (lengths[(i + 1) * width + j] >= lengths[i * width + j + 1]) {
      lines.push({ kind: "removed", text: a[i++] });
    } else {
      lines.push({ kind: "added", text: b[j++] });
    }
  }
  while (i < a.length) lines.push({ kind: "removed", text: a[i++] });
  while (j < b.length) lines.push({ kind: "added", text: b[j++] });
  return lines;
}
