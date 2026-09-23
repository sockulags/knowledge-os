import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { SyncFailure, SyncResult, SyncStatus } from "../api/types";
import { sync as syncApi, WRITE_EVENT, type Outcome } from "../api/write";

export interface SyncState {
  status: SyncStatus | null;
  busy: boolean;
  /** The last failed sync, shown until the next attempt or a dismissal. */
  failure: SyncFailure | null;
  /** The last successful sync from this window, for the sync page. */
  lastResult: SyncResult | null;
  refresh: () => void;
  run: () => Promise<Outcome<SyncResult>>;
  dismissFailure: () => void;
}

/** How often the status line re-reads the repository. Local only: the
 * status endpoint never contacts the remote. */
const POLL_MS = 20_000;

/** Git status for the shell's status line, plus the one sync action.
 * `onPulled` runs after a sync that brought in changes, so pages reload. */
export function useSync(onPulled: () => void): SyncState {
  const [status, setStatus] = useState<SyncStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<SyncFailure | null>(null);
  const [lastResult, setLastResult] = useState<SyncResult | null>(null);
  const pulledRef = useRef(onPulled);
  pulledRef.current = onPulled;

  const refresh = useCallback(() => {
    api.syncStatus().then(setStatus).catch(() => undefined);
  }, []);

  useEffect(() => {
    refresh();
    const timer = window.setInterval(refresh, POLL_MS);
    window.addEventListener("focus", refresh);
    window.addEventListener(WRITE_EVENT, refresh);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", refresh);
      window.removeEventListener(WRITE_EVENT, refresh);
    };
  }, [refresh]);

  const run = useCallback(async () => {
    setBusy(true);
    setFailure(null);
    setLastResult(null);
    const outcome = await syncApi.run();
    setBusy(false);
    if (outcome.ok) {
      setStatus(outcome.data.status);
      setLastResult(outcome.data);
      if (outcome.data.pulled > 0 || outcome.data.reindexed) pulledRef.current();
    } else {
      const failed = outcome.failure as SyncFailure;
      if (failed.status) setStatus(failed.status);
      else refresh();
      setFailure(failed);
      // A pull that stopped on conflicts has already changed the files.
      if (failed.error === "conflict") pulledRef.current();
    }
    return outcome;
  }, [refresh]);

  const dismissFailure = useCallback(() => setFailure(null), []);

  return { status, busy, failure, lastResult, refresh, run, dismissFailure };
}

/** "just now", "12 min ago", "3 h ago", or a date. */
export function relativeTime(iso: string, now = Date.now()): string {
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return iso;
  const minutes = Math.round((now - then) / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  return new Date(then).toLocaleDateString();
}
