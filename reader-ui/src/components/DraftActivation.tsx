import type { DraftActivation as DraftActivationData } from "../api/types";
import { write } from "../api/write";
import type { RunResult } from "../lib/pendingActions";
import { decisionKey, pendingActions, type DecisionEntry } from "../lib/pendingStore";

const linkClass = "font-medium text-(--color-accent-text) underline decoration-1 underline-offset-[3px]";

/** Start "Make active": the page shows the outcome at once and the write
 * waits a few seconds for Undo, like a decision action (see
 * lib/pendingActions.ts). It shares the page's pending key, so the Status row
 * and the reload after saving work as they do for a decision. */
export function startDraftActivation(id: string, sha: string, activation: DraftActivationData): void {
  pendingActions.schedule({
    key: decisionKey(id),
    kind: "activate",
    meta: { recordId: id, outcome: activation.outcome, labels: activation.labels, allowReason: false },
    run: async (_extra, options): Promise<RunResult> => {
      const outcome = await write.activate(id, sha, options);
      if (outcome.ok) return { ok: true };
      const { error, detail } = outcome.failure;
      return { ok: false, error, detail: error === "conflict" ? activation.labels.conflict : detail };
    },
  });
}

/** The box on the page of a draft that is not a decision (a note an agent
 * saved, a draft promoted from an observation): a sentence and "Make active".
 * A person decides; the server refuses the action from an agent. */
export function DraftActivation({
  id,
  sha,
  activation,
  pending = null,
}: {
  id: string;
  sha: string | null;
  activation: DraftActivationData;
  pending?: DecisionEntry | null;
}) {
  const labels = activation.labels;
  if (pending !== null) {
    const undoable = pending.state === "waiting" || pending.state === "paused";
    return (
      <section className="kos-card mb-8 mt-6 px-5 py-4" aria-label="Page actions">
        <p className="text-sm text-(--color-text)" role="status">
          {pending.meta.outcome.summary}{" "}
          {undoable && (
            <button type="button" className={linkClass} onClick={() => pendingActions.undo(pending.id)}>
              {labels.undo}
            </button>
          )}
          {pending.state === "saving" && <span className="text-(--color-text-faint)">{labels.saving}</span>}
        </p>
      </section>
    );
  }
  return (
    <section className="kos-card mb-8 mt-6 px-5 py-4" aria-label="Page actions">
      <p className="text-sm text-(--color-text)">{activation.summary}</p>
      {sha !== null && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            type="button"
            className="kos-btn kos-btn-primary"
            onClick={() => startDraftActivation(id, sha, activation)}
          >
            {activation.label}
          </button>
        </div>
      )}
    </section>
  );
}
