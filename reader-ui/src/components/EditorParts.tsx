import type { ReactNode } from "react";
import type { Blocker } from "react-router";
import { ConfirmDialog } from "./ConfirmDialog";

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-(--color-text-faint)">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-(--color-text-faint)">{hint}</span>}
    </label>
  );
}

export const inputClass =
  "w-full rounded-md border border-(--color-border) bg-(--color-bg-raised) px-3 py-1.5 text-sm outline-none focus:border-(--color-border-strong)";

/** "a, b , c" -> ["a", "b", "c"]; list fields are edited as comma-separated text. */
export function parseList(text: string): string[] {
  return text
    .split(",")
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
}

export function UnsavedChangesDialog({ blocker }: { blocker: Blocker }) {
  if (blocker.state !== "blocked") return null;
  return (
    <ConfirmDialog
      title="Leave without saving?"
      confirmLabel="Discard changes"
      tone="danger"
      onConfirm={() => blocker.proceed()}
      onCancel={() => blocker.reset()}
    >
      You have changes on this page that are not saved. Leaving discards them.
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
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="rounded-md bg-(--color-text) px-3.5 py-1.5 text-sm font-medium text-(--color-bg) hover:opacity-90 disabled:opacity-40"
    >
      {children}
    </button>
  );
}

export function SecondaryButton({ children, onClick }: { children: ReactNode; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="rounded-md border border-(--color-border) px-3.5 py-1.5 text-sm hover:bg-(--color-bg-hover)"
    >
      {children}
    </button>
  );
}
