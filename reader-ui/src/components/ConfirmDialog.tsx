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
  cancelLabel?: string;
  workingLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Focus a field if the dialog asks for one, otherwise Cancel, so a
    // stray Enter never confirms an action.
    const focusable = panelRef.current?.querySelector<HTMLElement>("textarea, input, button[data-cancel]");
    focusable?.focus();
  }, []);

  useEffect(() => {
    function handleKey(event: KeyboardEvent) {
      if (event.key === "Escape" && !busy) onCancel();
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [busy, onCancel]);

  const confirmClass =
    tone === "danger"
      ? "bg-(--color-accent-red-text) text-white hover:opacity-90"
      : "bg-(--color-text) text-(--color-bg) hover:opacity-90";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-label={title}>
      <div className="absolute inset-0 bg-black/30" onClick={() => !busy && onCancel()} />
      <div
        ref={panelRef}
        className="relative w-full max-w-[480px] rounded-xl border border-(--color-border) bg-(--color-bg-raised) p-5 shadow-xl"
      >
        <h2 className="text-base font-semibold">{title}</h2>
        <div className="mt-3 text-sm text-(--color-text-muted)">{children}</div>
        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            data-cancel
            onClick={onCancel}
            disabled={busy}
            className="rounded-md px-3 py-1.5 text-sm text-(--color-text-muted) hover:bg-(--color-bg-hover) disabled:opacity-50"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            data-confirm
            onClick={onConfirm}
            disabled={busy || confirmDisabled}
            className={`rounded-md px-3 py-1.5 text-sm font-medium disabled:opacity-50 ${confirmClass}`}
          >
            {busy ? workingLabel : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
