import { useCallback, useEffect, useState, useSyncExternalStore } from "react";
import { hasUnsavedChanges, subscribeUnsavedChanges } from "./useUnsavedChanges";

export interface PageReload {
  /** The key for the page's container: bumping it remounts the page so it
   * re-reads what changed on disk. */
  version: number;
  /** True while a reload waits for unsaved edits to be saved or discarded. */
  waiting: boolean;
  /** Reload the page now, or once no page holds unsaved edits. */
  request: () => void;
}

/** Reloads the shown page after a sync pulled changes or pending actions
 * were sent. A page with unsaved edits is never remounted under the person
 * typing: the reload waits and runs as soon as the edits are saved (or
 * discarded). */
export function usePageReload(): PageReload {
  const [version, setVersion] = useState(0);
  const [waiting, setWaiting] = useState(false);
  const unsaved = useSyncExternalStore(subscribeUnsavedChanges, hasUnsavedChanges);

  const request = useCallback(() => {
    if (hasUnsavedChanges()) setWaiting(true);
    else setVersion((value) => value + 1);
  }, []);

  useEffect(() => {
    if (!waiting || unsaved) return;
    setWaiting(false);
    setVersion((value) => value + 1);
  }, [waiting, unsaved]);

  return { version, waiting, request };
}
