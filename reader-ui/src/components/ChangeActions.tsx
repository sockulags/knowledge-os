import type { ChangeLabels, DecisionLanguage, ProposedChange, PropertyRow } from "../api/types";
import { changes, type Outcome } from "../api/write";
import type { PendingExtra, RunOptions, RunResult } from "../lib/pendingActions";
import { pendingActions, type DecisionEntry } from "../lib/pendingStore";

/** The pending-queue key of a proposed change (see lib/pendingStore.ts). */
export const changeKey = (id: string) => `change:${id}`;

function result(outcome: Outcome<unknown>): RunResult {
  if (outcome.ok) return { ok: true };
  return { ok: false, error: outcome.failure.error, detail: outcome.failure.detail };
}

// The queue's notice reads an outcome's notice; a change has no Status row.
const NO_STATUS: PropertyRow = { label: "", value: null };

/** Accept or discard a proposed change in one click: the row goes at once and
 * the write waits a few seconds for Undo, like a decision action. */
export function startChangeAction(
  change: Pick<ProposedChange, "id" | "content_sha256" | "outcomes">,
  action: "accept" | "discard",
  noticeLabels: DecisionLanguage["labels"],
): void {
  const run = async (_extra: PendingExtra, options: RunOptions): Promise<RunResult> =>
    result(
      action === "accept"
        ? await changes.accept(change.id, change.content_sha256, options)
        : await changes.discard(change.id, change.content_sha256, options),
    );
  pendingActions.schedule({
    key: changeKey(change.id),
    kind: action,
    meta: {
      recordId: changeKey(change.id),
      outcome: { notice: change.outcomes[action], summary: change.outcomes[action], status: NO_STATUS },
      labels: noticeLabels,
      allowReason: false,
    },
    run,
  });
}

/** Accept (unless the edit is stale) and Discard for one proposed change;
 * while an action waits for Undo it shows what will happen instead. */
export function ChangeActions({
  change,
  labels,
  noticeLabels,
  pending = null,
}: {
  change: ProposedChange;
  labels: ChangeLabels;
  noticeLabels: DecisionLanguage["labels"];
  pending?: DecisionEntry | null;
}) {
  if (pending !== null) {
    return (
      <div className="flex flex-wrap items-center gap-3 text-sm text-(--color-text-muted)">
        <span>{pending.meta.outcome.notice}</span>
        {(pending.state === "waiting" || pending.state === "paused") && (
          <button
            type="button"
            className="font-medium text-(--color-accent-text) underline decoration-1 underline-offset-[3px]"
            onClick={() => pendingActions.undo(pending.id)}
          >
            {noticeLabels.undo}
          </button>
        )}
      </div>
    );
  }
  return (
    <div className="flex flex-wrap items-center gap-2">
      {change.actions.accept && (
        <button
          type="button"
          className="kos-btn kos-btn-primary kos-btn-sm"
          onClick={() => startChangeAction(change, "accept", noticeLabels)}
        >
          {labels.accept}
        </button>
      )}
      <button
        type="button"
        className="kos-btn kos-btn-secondary kos-btn-sm"
        onClick={() => startChangeAction(change, "discard", noticeLabels)}
      >
        {labels.discard}
      </button>
      {change.stale && <span className="text-xs text-(--color-text-faint)">{labels.stale}</span>}
    </div>
  );
}
