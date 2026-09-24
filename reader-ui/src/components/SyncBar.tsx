import { Link, useNavigate } from "react-router";
import { AlertTriangle, ArrowDown, ArrowUp, GitBranch, RefreshCw, X } from "lucide-react";
import type { SyncState } from "../hooks/useSync";
import { relativeTime } from "../hooks/useSync";

const UNAVAILABLE: Record<string, string> = {
  not_a_repo: "Not in Git",
  git_missing: "Git not found",
  source_repo: "Source repo",
};

/** The shell's Git status line: branch, commits to push and to pull,
 * changes not yet committed, when this computer last synced, and the sync
 * button. Every part links to the sync page for the details. */
export function SyncBar({ sync }: { sync: SyncState }) {
  const navigate = useNavigate();
  const { status, busy } = sync;
  if (status === null) return null;

  if (!status.available) {
    return (
      <Link
        to="/sync"
        title={status.detail ?? undefined}
        className="flex items-center gap-1.5 rounded-(--radius-control) px-2 py-1 text-xs text-(--color-text-faint) transition-colors hover:bg-(--color-bg-hover) hover:text-(--color-text-muted)"
      >
        <GitBranch size={13} />
        {UNAVAILABLE[status.reason ?? ""] ?? "Sync unavailable"}
      </Link>
    );
  }

  if (status.merging) {
    return (
      <Link
        to="/sync"
        className="flex items-center gap-1.5 rounded-(--radius-control) border border-[color-mix(in_srgb,var(--color-accent-amber-text)_30%,transparent)] bg-(--color-accent-amber-bg) px-2.5 py-1 text-xs font-medium text-(--color-accent-amber-text) transition-[filter] hover:brightness-[0.97]"
      >
        <AlertTriangle size={13} />
        {status.conflicts > 0
          ? `Sync paused: ${status.conflicts} ${status.conflicts === 1 ? "conflict" : "conflicts"} to resolve`
          : "Sync paused: ready to finish"}
      </Link>
    );
  }

  const lastSync = status.last_sync ? `Synced ${relativeTime(status.last_sync)}` : "Never synced";

  return (
    <div className="flex min-w-0 items-center gap-1" data-testid="sync-bar">
      <Link
        to="/sync"
        className="flex min-w-0 items-center gap-2.5 rounded-(--radius-control) px-2 py-1 text-xs text-(--color-text-muted) tabular-nums transition-colors hover:bg-(--color-bg-hover)"
        title={`${status.upstream ? `${status.branch} tracks ${status.upstream}` : "This branch has no upstream to sync with"}. ${lastSync}.`}
      >
        <span className="flex items-center gap-1 font-medium text-(--color-text)">
          <GitBranch size={13} />
          <span className="max-w-40 truncate">{status.branch ?? "detached"}</span>
        </span>
        {status.upstream ? (
          <>
            <span className="flex items-center gap-0.5" aria-label={`${status.ahead} to push`}>
              <ArrowUp size={12} />
              {status.ahead}
            </span>
            <span className="flex items-center gap-0.5" aria-label={`${status.behind} to pull`}>
              <ArrowDown size={12} />
              {status.behind}
            </span>
          </>
        ) : (
          <span className="text-(--color-accent-amber-text)">No upstream</span>
        )}
        {status.uncommitted > 0 && (
          <span className="flex items-center gap-1 text-(--color-accent-amber-text)">
            <span className="h-1.5 w-1.5 rounded-full bg-current" />
            {status.uncommitted}
            <span className="hidden lg:inline">uncommitted</span>
          </span>
        )}
        {status.identity === null && <span className="text-(--color-accent-red-text)">No Git identity</span>}
        <span className="hidden truncate xl:inline">{lastSync}</span>
      </Link>
      <button
        type="button"
        disabled={busy}
        onClick={async () => {
          const outcome = await sync.run();
          if (!outcome.ok && outcome.failure.error === "conflict") navigate("/sync");
        }}
        className="kos-btn kos-btn-secondary kos-btn-sm gap-1.5 text-xs"
      >
        <RefreshCw size={13} className={busy ? "animate-spin" : undefined} />
        {busy ? "Syncing…" : "Sync"}
      </button>
    </div>
  );
}

/** A failed sync, under the header until dismissed or the next attempt. */
export function SyncFailureBanner({ sync }: { sync: SyncState }) {
  const { failure } = sync;
  if (failure === null || failure.error === "conflict") return null;
  return (
    <div
      role="alert"
      className="flex items-start gap-2.5 border-b border-[color-mix(in_srgb,var(--color-accent-red-text)_25%,transparent)] bg-(--color-accent-red-bg) px-4 py-2.5 text-sm text-(--color-accent-red-text)"
    >
      <AlertTriangle size={16} className="mt-0.5 shrink-0" />
      <div className="min-w-0 flex-1">
        <p className="font-medium">Sync did not finish.</p>
        <p className="mt-0.5 whitespace-pre-wrap break-words">{failure.detail}</p>
        {failure.issues && failure.issues.length > 0 && (
          <Link to="/sync" className="mt-1 inline-block font-medium underline underline-offset-2">
            See the lint issues
          </Link>
        )}
      </div>
      <button
        type="button"
        onClick={sync.dismissFailure}
        aria-label="Dismiss"
        className="rounded-[5px] p-0.5 opacity-80 hover:bg-[color-mix(in_srgb,currentColor_12%,transparent)] hover:opacity-100"
      >
        <X size={15} />
      </button>
    </div>
  );
}
