import { useEffect, useRef, type ReactNode } from "react";
import { useDialogFocus } from "../hooks/useDialogFocus";

/** A second action offered next to the main one (Discard beside Save). */
export interface DialogAction {
  label: string;
  tone?: "neutral" | "danger";
  onClick: () => void;
}

/** A small modal confirmation: what will happen, then Cancel or the action.
 * Escape and the backdrop cancel unless the action is running. Focus stays
 * inside while it is open and goes back to what opened it on close. */
export function ConfirmDialog({
  title,
  children,
  confirmLabel,
  tone = "neutral",
  busy = false,
  confirmDisabled = false,
  hideConfirm = false,
  alternative,
  cancelLabel = "Cancel",
  workingLabel = "Working…",
  onConfirm,
  onCancel,
}: {
  title: string;
  children: ReactNode;
  confirmLabel: string;
  tone?: "neutral" | "danger";
  busy?: boolean;
  confirmDisabled?: boolean;
  /** Only explain (why something cannot be done): the one button closes it. */
  hideConfirm?: boolean;
  alternative?: DialogAction;
  cancelLabel?: string;
  workingLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const panelRef = useRef<HTMLDivElement>(null);
  useDialogFocus(panelRef);

  useEffect(() => {
    // Focus a field if the dialog asks for one, otherwise Cancel, so a
    // stray Enter never confirms an action.
    const focusable = panelRef.current?.querySelector<HTMLElement>(
      "textarea:not(:disabled), input:not(:disabled), button[data-cancel]",
    );
    focusable?.focus();
  }, []);

  useEffect(() => {
    function handleKey(event: KeyboardEvent) {
      if (event.key === "Escape" && !busy) onCancel();
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [busy, onCancel]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-label={title}>
      <div className="kos-scrim absolute inset-0" onClick={() => !busy && onCancel()} />
      <div ref={panelRef} className="kos-overlay relative w-full max-w-[480px] p-6">
        <h2 className="kos-heading text-[19px]">{title}</h2>
        <div className="mt-3 text-sm leading-relaxed text-(--color-text-muted)">{children}</div>
        <div className="mt-6 flex justify-end gap-2">
          <button type="button" data-cancel onClick={onCancel} disabled={busy} className="kos-btn kos-btn-ghost">
            {cancelLabel}
          </button>
          {alternative && (
            <button
              type="button"
              data-alternative
              onClick={alternative.onClick}
              disabled={busy}
              className={`kos-btn ${alternative.tone === "danger" ? "kos-btn-danger" : "kos-btn-secondary"}`}
            >
              {alternative.label}
            </button>
          )}
          {!hideConfirm && (
            <button
              type="button"
              data-confirm
              onClick={onConfirm}
              disabled={busy || confirmDisabled}
              className={`kos-btn ${tone === "danger" ? "kos-btn-danger" : "kos-btn-primary"}`}
            >
              {busy ? workingLabel : confirmLabel}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
