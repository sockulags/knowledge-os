import { useEffect, useRef, useState, type ReactNode } from "react";
import type { Blocker } from "react-router";
import { ConfirmDialog } from "./ConfirmDialog";

/** The label over a form field. Shared with the dialogs that ask for a name
 * or a reason, so every field in the app is labelled the same way. */
export const fieldLabelClass = "mb-1.5 block text-[13px] font-medium text-(--color-text-muted)";

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className={fieldLabelClass}>{label}</span>
      {children}
      {hint && <span className="mt-1.5 block text-xs text-(--color-text-faint)">{hint}</span>}
    </label>
  );
}

export const inputClass = "kos-input";

/** "a, b , c" -> ["a", "b", "c"]; list fields are edited as comma-separated text. */
export function parseList(text: string): string[] {
  return text
    .split(",")
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
}

/** What an editor offers the leave dialog: its own save, and whether a save
 * can run now (not while one is running or an attachment is still stored). */
export interface LeaveSave {
  /** Resolves true once the changes are on disk; false keeps the person in
   * the editor, which shows why (a conflict, a refused write). */
  save: () => Promise<boolean>;
  canSave: boolean;
}

export function UnsavedChangesDialog({ blocker, save }: { blocker: Blocker; save?: LeaveSave }) {
  const [saving, setSaving] = useState(false);
  // The blocker as last rendered, so a finished save acts on the current one.
  const blockerRef = useRef(blocker);
  blockerRef.current = blocker;
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  if (blocker.state !== "blocked") return null;

  const discard = () => blocker.proceed();
  if (!save) {
    return (
      <ConfirmDialog
        title="Leave without saving?"
        confirmLabel="Discard changes"
        tone="danger"
        onConfirm={discard}
        onCancel={() => blocker.reset()}
      >
        You have changes on this page that are not saved. Leaving discards them.
      </ConfirmDialog>
    );
  }

  async function saveAndLeave() {
    setSaving(true);
    const ok = await save!.save();
    if (!mounted.current) return;
    setSaving(false);
    const current = blockerRef.current;
    if (current.state !== "blocked") return;
    if (ok) current.proceed();
    else current.reset();
  }

  return (
    <ConfirmDialog
      title="Leave without saving?"
      confirmLabel="Save and leave"
      workingLabel="Saving…"
      busy={saving}
      confirmDisabled={!save.canSave}
      alternative={{ label: "Discard changes", tone: "danger", onClick: discard }}
      onConfirm={() => void saveAndLeave()}
      onCancel={() => blocker.reset()}
    >
      You have changes on this page that are not saved. Save them before leaving, or leave and discard them.
    </ConfirmDialog>
  );
}

export function PrimaryButton({
  children,
  disabled,
  onClick,
}: {
  children: ReactNode;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button type="button" onClick={onClick} disabled={disabled} className="kos-btn kos-btn-primary">
      {children}
    </button>
  );
}

export function SecondaryButton({ children, onClick }: { children: ReactNode; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} className="kos-btn kos-btn-secondary">
      {children}
    </button>
  );
}
