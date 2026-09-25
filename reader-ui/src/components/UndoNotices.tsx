import { useEffect, useRef, useState, type CSSProperties } from "react";
import { AlertTriangle, CheckCircle2, Undo2, X } from "lucide-react";
import { pendingActions, usePendingEntries, type DecisionEntry } from "../lib/pendingStore";

/** How long a finished notice stays before it goes by itself. */
const DONE_MS = 3500;

/** The notices for one-click decision actions, bottom centre: what was done,
 * Undo while the write still waits, and for a withdrawal an optional reason.
 * Pointing at or focusing a notice stops its countdown, so it never runs out
 * while someone reads or types. They never block the page. */
export function UndoNotices() {
  const entries = usePendingEntries();
  if (entries.length === 0) return null;
  return (
    <div
      className="pointer-events-none fixed inset-x-0 bottom-4 z-50 flex flex-col items-center gap-2 px-4"
      data-testid="undo-notices"
    >
      {entries.map((entry) => (
        <Notice key={entry.id} entry={entry} />
      ))}
    </div>
  );
}

function Notice({ entry }: { entry: DecisionEntry }) {
  const labels = entry.meta.labels;
  const [reasonOpen, setReasonOpen] = useState(false);
  const [reason, setReason] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const undoable = entry.state === "waiting" || entry.state === "paused";
  const failed = entry.state === "failed";

  useEffect(() => {
    if (entry.state !== "done" && entry.state !== "undone") return;
    const timer = window.setTimeout(() => pendingActions.dismiss(entry.id), DONE_MS);
    return () => window.clearTimeout(timer);
  }, [entry.id, entry.state]);

  useEffect(() => {
    if (reasonOpen) inputRef.current?.focus();
  }, [reasonOpen]);

  function hold() {
    pendingActions.pause(entry.id);
  }
  function release() {
    if (!reasonOpen) pendingActions.resume(entry.id);
  }
  function saveReason() {
    pendingActions.setExtra(entry.id, { reason: reason.trim() || undefined });
    setReasonOpen(false);
    void pendingActions.flush(entry.id);
  }

  const text =
    entry.state === "undone" ? labels.undone : failed ? labels.failed : entry.meta.outcome.notice;

  return (
    <div
      role={failed ? "alert" : "status"}
      aria-live={failed ? "assertive" : "polite"}
      onMouseEnter={hold}
      onMouseLeave={release}
      onFocus={hold}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) release();
      }}
      className={`kos-overlay pointer-events-auto relative w-[min(460px,100%)] overflow-hidden rounded-(--radius-card) px-4 py-3 text-sm ${
        failed
          ? "border-[color-mix(in_srgb,var(--color-accent-red-text)_28%,transparent)] bg-(--color-accent-red-bg) text-(--color-accent-red-text)"
          : "text-(--color-text)"
      }`}
      data-testid="undo-notice"
      data-state={entry.state}
    >
      <div className="flex items-start gap-2.5">
        {failed ? (
          <AlertTriangle size={16} className="mt-0.5 shrink-0" />
        ) : entry.state === "undone" ? (
          <Undo2 size={16} className="mt-0.5 shrink-0 text-(--color-text-faint)" />
        ) : (
          <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-(--color-accent-green-text)" />
        )}
        <div className="min-w-0 flex-1">
          <p className={failed ? "font-medium" : ""}>{text}</p>
          {failed && entry.failure && <p className="mt-1 whitespace-pre-wrap break-words">{entry.failure.detail}</p>}
          {entry.state === "saving" && <p className="mt-0.5 text-xs text-(--color-text-faint)">{labels.saving}</p>}
          {reasonOpen && undoable && (
            <form
              className="mt-2 flex gap-2"
              onSubmit={(event) => {
                event.preventDefault();
                saveReason();
              }}
            >
              <input
                ref={inputRef}
                className="kos-input min-w-0 flex-1 px-2 py-1 text-sm"
                aria-label={labels.reason_label}
                placeholder={labels.reason_placeholder}
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    saveReason();
                  } else if (event.key === "Escape") {
                    event.stopPropagation();
                    setReasonOpen(false);
                    pendingActions.resume(entry.id);
                  }
                }}
              />
              <button type="submit" className="kos-btn kos-btn-secondary kos-btn-sm">
                {labels.save_reason}
              </button>
            </form>
          )}
        </div>
        {undoable && (
          <div className="flex shrink-0 items-center gap-1">
            {entry.meta.allowReason && !reasonOpen && (
              <button
                type="button"
                className="kos-btn kos-btn-ghost kos-btn-sm"
                onClick={() => {
                  pendingActions.pause(entry.id);
                  setReasonOpen(true);
                }}
              >
                {labels.add_reason}
              </button>
            )}
            <button
              type="button"
              className="kos-btn kos-btn-secondary kos-btn-sm"
              onClick={() => pendingActions.undo(entry.id)}
            >
              {labels.undo}
            </button>
          </div>
        )}
        {(failed || entry.state === "done" || entry.state === "undone") && (
          <button
            type="button"
            onClick={() => pendingActions.dismiss(entry.id)}
            aria-label={labels.dismiss}
            className="-m-0.5 shrink-0 rounded-[5px] p-0.5 opacity-70 transition-opacity hover:opacity-100"
          >
            <X size={15} />
          </button>
        )}
      </div>
      {undoable && (
        <span
          key={`${entry.state}-${entry.deadline ?? "paused"}`}
          aria-hidden="true"
          className="kos-notice-timer absolute bottom-0 left-0 h-0.5 bg-(--color-accent)"
          style={
            entry.state === "paused"
              ? { transform: `scaleX(${entry.remaining / pendingActions.delayMs})` }
              : ({
                  "--from": entry.remaining / pendingActions.delayMs,
                  animation: `kos-notice-timer ${entry.remaining}ms linear forwards`,
                } as CSSProperties)
          }
        />
      )}
    </div>
  );
}
