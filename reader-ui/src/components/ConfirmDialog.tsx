import { useEffect, useRef, type ReactNode } from "react";

/** A small modal confirmation: what will happen, then Cancel or the action.
 * Escape and the backdrop cancel unless the action is running. */
export function ConfirmDialog({
  title,
  children,
  confirmLabel,
  tone = "neutral",
  busy = false,
  confirmDisabled = false,
  hideConfirm = false,
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
  cancelLabel?: string;
  workingLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const panelRef = useRef<HTMLDivElement>(null);

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
