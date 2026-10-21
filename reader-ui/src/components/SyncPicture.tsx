import type { ReactNode } from "react";
import { ChevronLeft, ChevronRight, Cloud, CloudOff, GitMerge, Laptop } from "lucide-react";
import type { SyncStatus } from "../api/types";

function commits(count: number): string {
  return `${count} ${count === 1 ? "commit" : "commits"}`;
}

/** The sentence a screen reader hears for the picture. */
export function syncDescription(status: SyncStatus): string {
  const local = `This computer${status.branch ? ` (${status.branch})` : ""}`;
  if (status.upstream === null) return `${local} has nowhere to sync to yet.`;
  const parts = [`${commits(status.ahead)} to push`, `${commits(status.behind)} to pull`];
  let sentence = `${local} and ${status.upstream}: ${parts.join(", ")}.`;
  if (status.merging) {
    sentence +=
      status.conflicts > 0
        ? ` ${status.conflicts} ${status.conflicts === 1 ? "file has" : "files have"} changed on both sides and ${
            status.conflicts === 1 ? "needs" : "need"
          } a version.`
        : " A sync is waiting to be finished.";
  } else if (status.ahead === 0 && status.behind === 0) {
    sentence += " Both sides match as of the last sync.";
  }
  return sentence;
}

function Place({ icon, title, detail, dashed = false }: { icon: ReactNode; title: string; detail: string; dashed?: boolean }) {
  return (
    <div
      className={`flex min-w-0 flex-1 items-center gap-2.5 rounded-(--radius-card) border bg-(--color-bg-raised) px-3 py-2.5 ${
        dashed ? "border-dashed border-(--color-border-strong)" : "border-(--color-border)"
      }`}
    >
      <span className="shrink-0 text-(--color-text-muted)">{icon}</span>
      <span className="min-w-0">
        <span className="block truncate text-sm font-medium text-(--color-text)">{title}</span>
        <span className="block truncate text-xs text-(--color-text-faint)">{detail}</span>
      </span>
    </div>
  );
}

/** One direction of travel: a rule with an arrowhead and its count beside it.
 * Waiting commits draw the line in the accent colour; none, in the border. */
function Lane({ count, verb, direction }: { count: number; verb: string; direction: "push" | "pull" }) {
  const active = count > 0;
  const line = active ? "bg-(--color-accent)" : "bg-(--color-border-strong)";
  const head = active ? "text-(--color-accent)" : "text-(--color-border-strong)";
  // The push count sits above its arrow and the pull count below its own,
  // so each label is next to the line it describes.
  const caption = (
    <span
      className={`text-center text-xs leading-tight ${
        active ? "font-medium text-(--color-accent-text)" : "text-(--color-text-faint)"
      }`}
    >
      {active ? `${commits(count)} to ${verb}` : `Nothing to ${verb}`}
    </span>
  );
  return (
    <div data-lane={direction} data-count={count} className="flex flex-col items-stretch">
      {direction === "push" && caption}
      <span className="flex items-center">
        {direction === "pull" && <ChevronLeft size={14} className={`-mr-[7px] shrink-0 ${head}`} />}
        <span className={`h-[1.5px] flex-1 ${line}`} />
        {direction === "push" && <ChevronRight size={14} className={`-ml-[7px] shrink-0 ${head}`} />}
      </span>
      {direction === "pull" && caption}
    </div>
  );
}

/** The sync state as a picture: this computer on the left, the remote on the
 * right, and between them what waits to be pushed and pulled, or the
 * conflict a sync is stopped on. The rows below the picture keep the same
 * facts as text; the picture itself reads as one sentence to assistive
 * technology. Null when the knowledge base is not in Git. */
export function SyncPicture({ status }: { status: SyncStatus }) {
  if (!status.available) return null;
  const noRemote = status.upstream === null;
  const state = noRemote
    ? "no-remote"
    : status.merging
      ? "conflict"
      : status.ahead === 0 && status.behind === 0
        ? "in-step"
        : "waiting";
  return (
    <div
      role="img"
      aria-label={syncDescription(status)}
      data-state={state}
      className="kos-card mb-4 flex items-center gap-2 px-4 py-4 sm:gap-3"
    >
      <Place
        icon={<Laptop size={18} />}
        title="This computer"
        detail={
          status.uncommitted > 0 && !status.merging
            ? `${status.branch ?? "No branch"} · ${status.uncommitted} not committed`
            : (status.branch ?? "No branch")
        }
      />
      <div className="flex w-[34%] max-w-56 shrink-0 flex-col justify-center gap-1.5">
        {noRemote ? (
          <>
            <span className="text-center text-xs text-(--color-text-faint)">Not connected</span>
            <span className="border-t border-dashed border-(--color-border-strong)" />
          </>
        ) : (
          <>
            <Lane count={status.ahead} verb="push" direction="push" />
            {status.merging && (
              <span className="mx-auto inline-flex items-center gap-1 rounded-[5px] bg-(--color-accent-amber-bg) px-1.5 py-[3px] text-xs font-medium leading-none text-(--color-accent-amber-text)">
                <GitMerge size={12} />
                {status.conflicts > 0
                  ? `${status.conflicts} ${status.conflicts === 1 ? "conflict" : "conflicts"}`
                  : "Sync to finish"}
              </span>
            )}
            <Lane count={status.behind} verb="pull" direction="pull" />
          </>
        )}
      </div>
      <Place
        icon={noRemote ? <CloudOff size={18} /> : <Cloud size={18} />}
        title={noRemote ? "No remote" : (status.upstream ?? "")}
        detail={noRemote ? "Nothing to sync with yet" : "Remote"}
        dashed={noRemote}
      />
    </div>
  );
}
