import { useState } from "react";
import { Link } from "react-router";
import { ArrowRight } from "lucide-react";
import type { DecisionActions as DecisionActionsData, DecisionDialog, DecisionLanguage, WriteFailure } from "../api/types";
import { write, type Outcome } from "../api/write";
import { ConfirmDialog } from "./ConfirmDialog";
import { DecisionGuideToggle } from "./DecisionGuide";
import { WriteFailureCallout } from "./WriteFailureCallout";
import { inputClass } from "./EditorParts";

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

function DialogChanges({ dialog }: { dialog: DecisionDialog }) {
  return (
    <ul className="mt-3 space-y-2 rounded-lg border border-(--color-border) px-3 py-2.5">
      {dialog.changes.map((change, index) => (
        <li key={index}>
          {change.subject && <span className="block text-xs text-(--color-text-faint)">{change.subject}</span>}
          <span className="flex flex-wrap items-center gap-1.5 text-(--color-text)">
            <span>{change.from}</span>
            <ArrowRight size={13} className="text-(--color-text-faint)" />
            <span className="font-medium">{change.to}</span>
          </span>
        </li>
      ))}
      <li>{dialog.history}</li>
    </ul>
  );
}

const buttonClass =
  "rounded-md border border-(--color-border) bg-(--color-bg-raised) px-3 py-1.5 text-sm font-medium hover:border-(--color-border-strong) hover:bg-(--color-bg-hover)";

/** Accept, withdraw, or accept-as-replacement for a decision, each behind a
 * confirmation that says what will change and whether it can be undone.
 * Which buttons appear and every word in the dialogs come from the API; the
 * core re-checks every rule. The "page" variant is the box on a decision
 * page (with its summary sentence and the "How decisions work" link); the
 * "inline" variant is just the buttons, for an inbox row. */
export function DecisionActions({
  target,
  language,
  onDone,
  variant = "page",
}: {
  target: DecisionTarget;
  language: DecisionLanguage;
  onDone: (action: Action) => void;
  variant?: "page" | "inline";
}) {
  const { actions, content_sha256: sha } = target;
  const labels = language.labels;
  const [open, setOpen] = useState<Action | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<WriteFailure | null>(null);

  const replaces = actions.supersede;
  const hasButtons =
    sha !== null && (actions.accept || actions.withdraw || replaces !== null || actions.propose_replacement);

  function close() {
    setOpen(null);
    setFailure(null);
    setReason("");
  }

  async function run(action: Action) {
    setBusy(true);
    setFailure(null);
    let outcome: Outcome<unknown>;
    if (action === "accept") outcome = await write.accept(target.id, sha!);
    else if (action === "withdraw") outcome = await write.withdraw(target.id, sha!, reason.trim());
    else outcome = await write.supersede(target.id, sha!, replaces!.id, replaces!.content_sha256 ?? "");
    setBusy(false);
    if (outcome.ok) {
      close();
      onDone(action);
    } else {
      setFailure(outcome.failure);
    }
  }

  const failureView =
    failure === null ? null : (
      <div className="mt-3">
        <WriteFailureCallout failure={failure.error === "conflict" ? { ...failure, detail: labels.conflict } : failure} />
      </div>
    );

  const dialogProps = { busy, cancelLabel: labels.cancel, workingLabel: labels.working, onCancel: close };
  const dialogs = actions.dialogs;

  const buttons = hasButtons ? (
    <div className={variant === "page" ? "mt-3 flex flex-wrap gap-2" : "flex flex-wrap gap-2"}>
      {actions.accept && dialogs.accept && (
        <button type="button" className={buttonClass} onClick={() => setOpen("accept")}>
          {labels.accept}
        </button>
      )}
      {replaces !== null && dialogs.supersede && (
        <button type="button" className={buttonClass} onClick={() => setOpen("supersede")}>
          {labels.accept_replacement}
        </button>
      )}
      {actions.withdraw && dialogs.withdraw && (
        <button type="button" className={buttonClass} onClick={() => setOpen("withdraw")}>
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
    </div>
  ) : null;

  const dialogViews = (
    <>
      {open === "accept" && dialogs.accept && (
        <ConfirmDialog title={dialogs.accept.title} confirmLabel={dialogs.accept.confirm} onConfirm={() => void run("accept")} {...dialogProps}>
          <p>{dialogs.accept.body}</p>
          <DialogChanges dialog={dialogs.accept} />
          {failureView}
        </ConfirmDialog>
      )}

      {open === "withdraw" && dialogs.withdraw && (
        <ConfirmDialog
          title={dialogs.withdraw.title}
          confirmLabel={dialogs.withdraw.confirm}
          tone="danger"
          confirmDisabled={reason.trim() === ""}
          onConfirm={() => void run("withdraw")}
          {...dialogProps}
        >
          <p>{dialogs.withdraw.body}</p>
          <DialogChanges dialog={dialogs.withdraw} />
          <label className="mt-3 block">
            <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-(--color-text-faint)">
              {labels.reason_label}
            </span>
            <textarea
              className={`${inputClass} min-h-[4.5rem] resize-y`}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder={labels.reason_placeholder}
            />
          </label>
          {failureView}
        </ConfirmDialog>
      )}

      {open === "supersede" && replaces !== null && dialogs.supersede && (
        <ConfirmDialog
          title={dialogs.supersede.title}
          confirmLabel={dialogs.supersede.confirm}
          onConfirm={() => void run("supersede")}
          {...dialogProps}
        >
          <p>{dialogs.supersede.body}</p>
          <DialogChanges dialog={dialogs.supersede} />
          <p className="mt-3">
            <Link to={`/r/${target.id}/compare`} className="underline underline-offset-2">
              {labels.compare}
            </Link>
          </p>
          {failureView}
        </ConfirmDialog>
      )}
    </>
  );

  if (variant === "inline") {
    return (
      <>
        {buttons}
        {dialogViews}
      </>
    );
  }

  return (
    <section className="mb-8 mt-6 rounded-lg border border-(--color-border) bg-(--color-bg-sidebar) px-4 py-3" aria-label="Decision actions">
      {actions.summary && <p className="text-sm text-(--color-text-muted)">{actions.summary}</p>}
      {buttons}
      <div className={actions.summary || buttons ? "mt-3" : ""}>
        <DecisionGuideToggle language={language} />
      </div>
      {dialogViews}
    </section>
  );
}
