// How the project tree lays out deep folders: the indent each level gets,
// and the trail of folders from a project down to a focused folder. No
// React and no DOM here, so `npm test` can run it under Node.

import type { TreeNode } from "../api/types.ts";
import { folderDisplayName } from "./text.ts";

/** Levels that get the full indent; deeper levels get the compact one. */
export const FULL_INDENT_LEVELS = 3;

/** One nesting level's indent, in pixels: the gap before its guide line
 * and the gap after it. The full step puts the guide under the parent's
 * chevron; the compact step keeps a deep title's room while the guides
 * still show one line per level. */
export interface Indent {
  margin: number;
  padding: number;
}

export const FULL_INDENT: Indent = { margin: 10, padding: 6 };
export const COMPACT_INDENT: Indent = { margin: 3, padding: 4 };

/** The indent of the container that holds nesting level `level` (1 is a
 * project's or a focused folder's own contents). */
export function indentFor(level: number): Indent {
  return level <= FULL_INDENT_LEVELS ? FULL_INDENT : COMPACT_INDENT;
}

/** How a folder is named in the tree: its own page's title, or its folder
 * name made readable. */
export function folderTitle(node: TreeNode): string {
  return node.overview?.title ?? folderDisplayName(node.name);
}

export interface TrailStep {
  path: string;
  title: string;
}

/** The folders from a project's top level down to the folder at `path`,
 * both included, or null when no such folder exists (it was moved or
 * renamed). The project itself is not part of the trail. */
export function folderTrail(tree: TreeNode, path: string): TrailStep[] | null {
  if (path === "") return null;
  for (const child of tree.children) {
    if (child.path === path) return [{ path: child.path, title: folderTitle(child) }];
    if (path.startsWith(`${child.path}/`)) {
      const rest = folderTrail(child, path);
      if (rest !== null) return [{ path: child.path, title: folderTitle(child) }, ...rest];
    }
  }
  return null;
}

/** Whether `path` is `folder` itself or somewhere inside it. */
export function isWithin(path: string, folder: string): boolean {
  return path === folder || path.startsWith(`${folder}/`);
}

/** Which folder the tree should open down to after the shown folder
 * changes from `previous` to `next` (null is the whole project). Going up
 * keeps the way back down to where the person was open; going down, or
 * sideways, opens the new folder. */
export function revealAfterFocus(previous: string | null, next: string | null): string | null {
  if (previous !== null && (next === null || isWithin(previous, next))) return previous;
  return next;
}

/** The folder at `path`, or null when there is none. */
export function findFolder(tree: TreeNode, path: string): TreeNode | null {
  for (const child of tree.children) {
    if (child.path === path) return child;
    if (path.startsWith(`${child.path}/`)) {
      const found = findFolder(child, path);
      if (found !== null) return found;
    }
  }
  return null;
}
