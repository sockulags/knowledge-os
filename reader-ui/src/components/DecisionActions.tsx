import { useState, type ReactNode } from "react";
import { Link } from "react-router";
import { ArrowRight } from "lucide-react";
import type { RecordPayload, WriteFailure } from "../api/types";
import { write, type Outcome } from "../api/write";
import { ConfirmDialog } from "./ConfirmDialog";
import { WriteFailureCallout } from "./WriteFailureCallout";
import { inputClass } from "./EditorParts";

type Action = "accept" | "withdraw" | "supersede";

function Change({ from, to }: { from: string; to: string }) {
  return (
    <span className="flex flex-wrap items-center gap-1.5 text-(--color-text)">
      <span>{from}</span>
      <ArrowRight size={13} className="text-(--color-text-faint)" />
      <span className="font-medium">{to}</span>
    </span>
  );
}

function ChangeList({ children }: { children: ReactNode }) {
  return <ul className="mt-3 space-y-2 rounded-lg border border-(--color-border) px-3 py-2.5">{children}</ul>;
}

const buttonClass =
  "rounded-md border border-(--color-border) bg-(--color-bg-raised) px-3 py-1.5 text-sm font-medium hover:border-(--color-border-strong) hover:bg-(--color-bg-hover)";

/** Accept, withdraw, or accept-as-replacement for a decision, each behind a
 * confirmation that says what will change. Which buttons appear comes from
 * the API (`editing.decision_actions`); the core re-checks every rule. */
export function DecisionActions({ record, onDone }: { record: RecordPayload; onDone: () => void }) {
  const actions = record.editing.decision_actions;
  const sha = record.editing.content_sha256;
  const [open, setOpen] = useState<Action | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<WriteFailure | null>(null);

  if (actions === null || sha === null) return null;
  const replaces = actions.supersede;
  const hasButtons = actions.accept || actions.withdraw || replaces !== null || actions.propose_replacement;
  if (!hasButtons) return null;

  function close() {
    setOpen(null);
    setFailure(null);
    setReason("");
  }

  async function run(action: Action) {
    setBusy(true);
    setFailure(null);
    let outcome: Outcome<unknown>;
    if (action === "accept") outcome = await write.accept(record.id, sha!);
    else if (action === "withdraw") outcome = await write.withdraw(record.id, sha!, reason.trim());
    else outcome = await write.supersede(record.id, sha!, replaces!.id, replaces!.content_sha256 ?? "");
    setBusy(false);
    if (outcome.ok) {
      close();
      onDone();
    } else {
      setFailure(outcome.failure);
    }
  }

  const failureView =
    failure === null ? null : failure.error === "conflict" ? (
      <div className="mt-3">
        <WriteFailureCallout failure={{ ...failure, detail: "A file changed on disk after this page was loaded. Nothing was changed; close this and reload the page to see the current version." }} />
      </div>
    ) : (
      <div className="mt-3">
        <WriteFailureCallout failure={failure} />
      </div>
    );

  return (
    <section className="mb-8 mt-6 rounded-lg border border-(--color-border) bg-(--color-bg-sidebar) px-4 py-3" aria-label="Decision actions">
      <p className="text-sm text-(--color-text-muted)">
        {replaces !== null
          ? `This proposal would replace “${replaces.title}”, which is in force now.`
          : actions.withdraw
            ? "This proposal is waiting on a decision."
            : "This decision is in force."}
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        {actions.accept && (
          <button type="button" className={buttonClass} onClick={() => setOpen("accept")}>
            Accept decision
          </button>
        )}
        {replaces !== null && (
          <button type="button" className={buttonClass} onClick={() => setOpen("supersede")}>
            Accept as replacement
          </button>
        )}
        {actions.withdraw && (
          <button type="button" className={buttonClass} onClick={() => setOpen("withdraw")}>
            Withdraw proposal
          </button>
        )}
        {actions.propose_replacement && record.editing.project_id && (
          <Link
            className={buttonClass}
            to={`/p/${record.editing.project_id}/new?kind=decision&supersedes=${encodeURIComponent(record.id)}&folder=${encodeURIComponent(record.editing.folder)}`}
          >
            Propose a replacement
          </Link>
        )}
      </div>

      {open === "accept" && (
        <ConfirmDialog title="Accept this decision?" confirmLabel="Accept" busy={busy} onConfirm={() => void run("accept")} onCancel={close}>
          <p>“{record.title}” starts to govern this project.</p>
          <ChangeList>
            <li><Change from="Proposal" to="In force, accepted today" /></li>
            <li>The acceptance is recorded in the page's history.</li>
          </ChangeList>
          {failureView}
        </ConfirmDialog>
      )}

      {open === "withdraw" && (
        <ConfirmDialog
          title="Withdraw this proposal?"
          confirmLabel="Withdraw"
          tone="danger"
          busy={busy}
          confirmDisabled={reason.trim() === ""}
          onConfirm={() => void run("withdraw")}
          onCancel={close}
        >
          <p>“{record.title}” stops being considered. It was never accepted and cannot be accepted later.</p>
          <ChangeList>
            <li><Change from="Proposal" to="Archived, withdrawn without being accepted" /></li>
            <li>Your reason is recorded with it.</li>
          </ChangeList>
          <label className="mt-3 block">
            <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-(--color-text-faint)">Reason</span>
            <textarea
              className={`${inputClass} min-h-[4.5rem] resize-y`}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder="Why this proposal is being dropped"
            />
          </label>
          {failureView}
        </ConfirmDialog>
      )}

      {open === "supersede" && replaces !== null && (
        <ConfirmDialog
          title="Accept as the replacement?"
          confirmLabel="Accept replacement"
          busy={busy}
          onConfirm={() => void run("supersede")}
          onCancel={close}
        >
          <p>Both decisions change together.</p>
          <ChangeList>
            <li>
              <span className="block text-xs text-(--color-text-faint)">{record.title}</span>
              <Change from="Proposal" to="In force, accepted today" />
            </li>
            <li>
              <span className="block text-xs text-(--color-text-faint)">{replaces.title}</span>
              <Change from="In force" to={`Replaced by “${record.title}”`} />
            </li>
          </ChangeList>
          <p className="mt-3">
            <Link to={`/r/${record.id}/compare`} className="underline underline-offset-2">
              Compare the two first
            </Link>
          </p>
          {failureView}
        </ConfirmDialog>
      )}
    </section>
  );
}
