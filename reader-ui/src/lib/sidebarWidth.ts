// The sidebar's width: its limits, keyboard steps, and where the chosen
// width is remembered. No React and no DOM here beyond the storage and
// bridge objects passed in, so `npm test` can run it under Node.
//
// The width lives in the `--sidebar-width` CSS variable on the root
// element; the drag handle writes that variable directly while it moves,
// so resizing never re-renders the tree.

/** The width the sidebar opens at, and returns to on double-click. */
export const DEFAULT_WIDTH = 256;
export const MIN_WIDTH = 200;
export const MAX_WIDTH = 560;
/** The reading column never gets narrower than this because of the sidebar. */
export const MIN_MAIN_WIDTH = 420;
/** Arrow keys move the handle by this much; Shift+arrow by the larger step. */
export const KEY_STEP = 16;
export const KEY_STEP_LARGE = 64;

export const STORAGE_KEY = "kos-reader-sidebar-width";
export const CSS_VARIABLE = "--sidebar-width";

/** The widest the sidebar may be in a window `viewport` pixels wide. */
export function maxWidthFor(viewport: number): number {
  return Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, Math.floor(viewport - MIN_MAIN_WIDTH)));
}

/** `width` kept inside the limits, rounded to whole pixels. A missing or
 * non-finite width becomes the default. */
export function clampWidth(width: number, viewport = Number.POSITIVE_INFINITY): number {
  if (!Number.isFinite(width)) return Math.min(DEFAULT_WIDTH, maxWidthFor(viewport));
  return Math.min(Math.max(Math.round(width), MIN_WIDTH), maxWidthFor(viewport));
}

/** A stored value as a width, or null when it is missing or not a number
 * in range (a damaged or hand-edited value falls back to the default). */
export function parseStoredWidth(value: unknown): number | null {
  const number = typeof value === "string" && value.trim() !== "" ? Number(value) : value;
  if (typeof number !== "number" || !Number.isFinite(number)) return null;
  if (number < MIN_WIDTH || number > MAX_WIDTH) return null;
  return Math.round(number);
}

/** The width after a key press on the focused handle, or null for a key
 * that does not resize. Home and End jump to the limits. */
export function widthForKey(width: number, key: string, shift: boolean, viewport: number): number | null {
  const step = shift ? KEY_STEP_LARGE : KEY_STEP;
  switch (key) {
    case "ArrowLeft":
      return clampWidth(width - step, viewport);
    case "ArrowRight":
      return clampWidth(width + step, viewport);
    case "Home":
      return MIN_WIDTH;
    case "End":
      return maxWidthFor(viewport);
    default:
      return null;
  }
}

/** Where a width can be kept. The browser's storage is one; the desktop
 * app adds its own settings file, because the reader it loads runs on a
 * new local port each launch and browser storage is kept per origin. */
export interface WidthStore {
  load: () => number | null;
  save: (width: number | null) => void;
}

/** Browser storage, where reading or writing can throw (a private window,
 * blocked site data); then the width is simply not remembered. */
export function browserStore(storage: () => Pick<Storage, "getItem" | "setItem" | "removeItem">): WidthStore {
  return {
    load: () => {
      try {
        return parseStoredWidth(storage().getItem(STORAGE_KEY));
      } catch {
        return null;
      }
    },
    save: (width) => {
      try {
        if (width === null) storage().removeItem(STORAGE_KEY);
        else storage().setItem(STORAGE_KEY, String(width));
      } catch {
        // Best effort: the width still applies for this session.
      }
    },
  };
}

/** The desktop app's bridge, when the reader runs inside it. */
export interface DesktopWidthBridge {
  getSidebarWidth: () => unknown;
  setSidebarWidth: (width: number | null) => void;
}

export function desktopStore(bridge: DesktopWidthBridge): WidthStore {
  return {
    load: () => {
      try {
        return parseStoredWidth(bridge.getSidebarWidth());
      } catch {
        return null;
      }
    },
    save: (width) => {
      try {
        bridge.setSidebarWidth(width);
      } catch {
        // The app may be closing; nothing to do.
      }
    },
  };
}

/** The first remembered width among `stores`, in order, or null. */
export function loadWidth(stores: WidthStore[]): number | null {
  for (const store of stores) {
    const width = store.load();
    if (width !== null) return width;
  }
  return null;
}

/** Remember `width` everywhere; null (the default) forgets it. */
export function saveWidth(stores: WidthStore[], width: number | null): void {
  for (const store of stores) store.save(width === DEFAULT_WIDTH ? null : width);
}
