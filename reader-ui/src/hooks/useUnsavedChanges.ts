import { useCallback, useEffect, useRef } from "react";
import { useBlocker, type Blocker } from "react-router";

/** How many mounted pages hold unsaved edits right now. Structure changes
 * (moving or renaming pages and folders) rewrite files and reload the page,
 * so they wait until this is zero instead of risking typed text. */
let unsavedPages = 0;
const listeners = new Set<() => void>();

function setUnsavedPages(count: number): void {
  unsavedPages = count;
  for (const listener of listeners) listener();
}

export function hasUnsavedChanges(): boolean {
  return unsavedPages > 0;
}

/** Calls `listener` whenever the count changes; returns the unsubscribe.
 * Shaped for `useSyncExternalStore` with `hasUnsavedChanges`. */
export function subscribeUnsavedChanges(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Warn before losing unsaved edits: an in-app navigation is held by the
 * returned blocker (the page shows its own confirm dialog), and a reload or
 * window close raises the browser's native prompt, which the desktop shell
 * turns into its own dialog.
 *
 * `allowNextNavigation` lets a page navigate right after a successful save,
 * before React has re-rendered with the clean state. */
export function useUnsavedChanges(dirty: boolean): { blocker: Blocker; allowNextNavigation: () => void } {
  const dirtyRef = useRef(dirty);
  dirtyRef.current = dirty;

  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      dirtyRef.current && currentLocation.pathname !== nextLocation.pathname,
  );

  useEffect(() => {
    if (!dirty) return;
    setUnsavedPages(unsavedPages + 1);
    function handleBeforeUnload(event: BeforeUnloadEvent) {
      if (!dirtyRef.current) return;
      event.preventDefault();
      // Older engines (and Electron's will-prevent-unload) look at returnValue.
      event.returnValue = "";
    }
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => {
      setUnsavedPages(unsavedPages - 1);
      window.removeEventListener("beforeunload", handleBeforeUnload);
    };
  }, [dirty]);

  const allowNextNavigation = useCallback(() => {
    dirtyRef.current = false;
  }, []);

  return { blocker, allowNextNavigation };
}
