// The app's one queue of one-click actions waiting out their undo window
// (see pendingActions.ts), and the React hooks that read it.

import { useEffect, useSyncExternalStore } from "react";
import type { DecisionLanguage, DecisionOutcome } from "../api/types";
import { PendingQueue, UNDO_WINDOW_MS, type PendingEntry } from "./pendingActions";

/** What the notice and the pages need to show a pending decision action. */
export interface DecisionPendingMeta {
  recordId: string;
  outcome: DecisionOutcome;
  labels: DecisionLanguage["labels"];
  /** Withdrawing offers "Add a reason" in its notice. */
  allowReason: boolean;
}

export type DecisionEntry = PendingEntry<DecisionPendingMeta>;

export const pendingActions = new PendingQueue<DecisionPendingMeta>(UNDO_WINDOW_MS, {
  now: () => Date.now(),
  setTimer: (callback, ms) => window.setTimeout(callback, ms),
  clearTimer: (handle) => window.clearTimeout(handle as number),
});

export const decisionKey = (recordId: string) => `decision:${recordId}`;

/** Dispatched on `window` when a pending write has finished (saved or failed),
 * so views reload what the core now holds. */
export const PENDING_SETTLED_EVENT = "kos:pending-settled";

let settled = new Set<number>();
pendingActions.subscribe(() => {
  const finished = pendingActions
    .snapshot()
    .filter((entry) => entry.state === "done" || entry.state === "failed")
    .map((entry) => entry.id);
  const fresh = finished.filter((id) => !settled.has(id));
  settled = new Set(finished);
  if (fresh.length > 0) window.dispatchEvent(new Event(PENDING_SETTLED_EVENT));
});

declare global {
  interface Window {
    /** The desktop app calls this and waits for it before it stops the core
     * (switching knowledge base, closing the window, quitting), so a write
     * still waiting for Undo is saved rather than lost. */
    kosFlushPendingActions?: () => Promise<number>;
  }
}

window.kosFlushPendingActions = () => pendingActions.flushAll({ keepalive: false });

export function usePendingEntries(): readonly DecisionEntry[] {
  return useSyncExternalStore(pendingActions.subscribe, pendingActions.snapshot);
}

/** Run `callback` whenever a pending write finishes. */
export function useOnPendingSettled(callback: () => void): void {
  useEffect(() => {
    window.addEventListener(PENDING_SETTLED_EVENT, callback);
    return () => window.removeEventListener(PENDING_SETTLED_EVENT, callback);
  }, [callback]);
}
