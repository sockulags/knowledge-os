import { Link } from "react-router";
import type { DecisionActions as DecisionActionsData, DecisionLanguage, WriteFailure } from "../api/types";
import { write, type Outcome } from "../api/write";
import type { PendingExtra, RunOptions, RunResult } from "../lib/pendingActions";
import { decisionKey, pendingActions, type DecisionEntry } from "../lib/pendingStore";
import { DecisionGuideToggle } from "./DecisionGuide";

type Action = "accept" | "withdraw" | "supersede";

/** What the action buttons act on: a decision page or an inbox row. */
export interface DecisionTarget {
  id: string;
  title: string;
  content_sha256: string | null;
  actions: DecisionActionsData;
  project_id: string | null;
  folder: string;
}

// Accepting is the step a proposal waits for, so it is the one primary
// button; withdrawing and replacing are secondary.
const primaryClass = "kos-btn kos-btn-primary";
const buttonClass = "kos-btn kos-btn-secondary";
const linkClass = "font-medium text-(--color-accent-text) underline decoration-1 underline-offset-[3px]";

function result(outcome: Outcome<unknown>, conflict: string): RunResult {
  if (outcome.ok) return { ok: true };
  const failure: WriteFailure = outcome.failure;
  return { ok: false, error: failure.error, detail: failure.error === "conflict" ? conflict : failure.detail };
}

/** Start one decision action: the interface shows its outcome at once and the
 * write waits a few seconds for Undo (see lib/pendingActions.ts). */
export function startDecisionAction(target: DecisionTarget, action: Action, language: DecisionLanguage): void {
  const { actions, content_sha256: sha } = target;
  const outcome = actions.outcomes[action];
  if (sha === null || outcome === undefined) return;
  const replaces = actions.supersede;
  const conflict = language.labels.conflict;
  const run = async (extra: PendingExtra, options: RunOptions): Promise<RunResult> => {
    if (action === "accept") return result(await write.accept(target.id, sha, options), conflict);
    if (action === "withdraw") return result(await write.withdraw(target.id, sha, extra.reason, options), conflict);
    return result(
      await write.supersede(target.id, sha, replaces!.id, replaces!.content_sha256 ?? "", options),
      conflict,
    );
  };
  pendingActions.schedule({
    key: decisionKey(target.id),
    kind: action,
    meta: { recordId: target.id, outcome, labels: language.labels, allowReason: action === "withdraw" },
    run,
  });
}

/** Accept, withdraw, or accept-as-replacement for a decision, each in one
 * click with no dialog. While the write waits for Undo (or runs), `pending`
 * is its entry and the box shows the outcome instead of the buttons. Which
 * buttons appear and every word come from the API; the core re-checks every
 * rule. The "page" variant is the box on a decision page (with its summary
 * sentence and the "How decisions work" link); the "inline" variant is just
 * the buttons, for an inbox row. */
export function DecisionActions({
  target,
  language,
  pending = null,
  variant = "page",
}: {
  target: DecisionTarget;
  language: DecisionLanguage;
  pending?: DecisionEntry | null;
  variant?: "page" | "inline";
}) {
  const { actions, content_sha256: sha } = target;
  const labels = language.labels;
  const replaces = actions.supersede;
  const hasButtons =
    sha !== null && (actions.accept || actions.withdraw || replaces !== null || actions.propose_replacement);

  if (pending !== null) {
    const undoable = pending.state === "waiting" || pending.state === "paused";
    const box = (
      <p className="text-sm text-(--color-text)" role="status">
        {pending.meta.outcome.summary}{" "}
        {undoable && (
          <button type="button" className={linkClass} onClick={() => pendingActions.undo(pending.id)}>
            {labels.undo}
          </button>
        )}
        {pending.state === "saving" && <span className="text-(--color-text-faint)">{labels.saving}</span>}
      </p>
    );
    if (variant === "inline") return box;
    return (
      <section className="kos-card mb-8 mt-6 px-5 py-4" aria-label="Decision actions">
        {box}
        <div className="mt-4 border-t border-(--color-border) pt-3">
          <DecisionGuideToggle language={language} />
        </div>
      </section>
    );
  }

  const buttons = hasButtons ? (
    <div className={variant === "page" ? "mt-3 flex flex-wrap items-center gap-2" : "flex flex-wrap items-center gap-2"}>
      {actions.accept && actions.outcomes.accept && (
        <button type="button" className={primaryClass} onClick={() => startDecisionAction(target, "accept", language)}>
          {labels.accept}
        </button>
      )}
      {replaces !== null && actions.outcomes.supersede && (
        <button
          type="button"
          className={primaryClass}
          onClick={() => startDecisionAction(target, "supersede", language)}
        >
          {labels.accept_replacement}
        </button>
      )}
      {actions.withdraw && actions.outcomes.withdraw && (
        <button
          type="button"
          className={buttonClass}
          onClick={() => startDecisionAction(target, "withdraw", language)}
        >
          {labels.withdraw}
        </button>
      )}
      {variant === "page" && actions.propose_replacement && target.project_id && (
        <Link
          className={buttonClass}
          to={`/p/${target.project_id}/new?kind=decision&supersedes=${encodeURIComponent(target.id)}&folder=${encodeURIComponent(target.folder)}`}
        >
          {labels.replace_with}
        </Link>
      )}
      {variant === "page" && replaces !== null && (
        <Link to={`/r/${target.id}/compare`} className={`${linkClass} ml-1 text-sm`}>
          {labels.compare_short}
        </Link>
      )}
    </div>
  ) : null;

  if (variant === "inline") return buttons;

  return (
    <section className="kos-card mb-8 mt-6 px-5 py-4" aria-label="Decision actions">
      {actions.summary && <p className="text-sm text-(--color-text)">{actions.summary}</p>}
      {buttons}
      <div className={actions.summary || buttons ? "mt-4 border-t border-(--color-border) pt-3" : ""}>
        <DecisionGuideToggle language={language} />
      </div>
    </section>
  );
}
