import type { ReactNode } from "react";
import { AlertTriangle, Info, GitCompare } from "lucide-react";
import { Link } from "react-router";

type Tone = "neutral" | "danger" | "lineage";

// Neutral notes sit on the sidebar tone; danger is the only red callout, so
// red keeps meaning "this went wrong"; lineage (a decision that replaces or
// was replaced by another) takes the ink tint of things you can follow.
const TONE_CLASSES: Record<Tone, string> = {
  neutral: "border-(--color-border) bg-(--color-bg-sidebar) text-(--color-text-muted)",
  danger:
    "border-[color-mix(in_srgb,var(--color-accent-red-text)_28%,transparent)] bg-(--color-accent-red-bg) text-(--color-accent-red-text)",
  lineage:
    "border-[color-mix(in_srgb,var(--color-accent)_28%,transparent)] bg-(--color-accent-ink-bg) text-(--color-text)",
};

const ICON_CLASSES: Record<Tone, string> = {
  neutral: "text-(--color-text-faint)",
  danger: "",
  lineage: "text-(--color-accent-text)",
};

export function Callout({
  tone = "neutral",
  icon,
  children,
}: {
  tone?: Tone;
  icon?: ReactNode;
  children: ReactNode;
}) {
  const defaultIcon = tone === "danger" ? <AlertTriangle size={16} /> : <Info size={16} />;
  return (
    <div
      className={`mb-6 flex items-start gap-3 rounded-(--radius-card) border px-4 py-3 text-sm leading-relaxed ${TONE_CLASSES[tone]}`}
    >
      <div className={`mt-0.5 shrink-0 ${ICON_CLASSES[tone]}`}>{icon ?? defaultIcon}</div>
      <div className="min-w-0">{children}</div>
    </div>
  );
}

/** A view that could not load at all: the danger callout, placed where the
 * page's own content would have been. */
export function LoadError({ children }: { children: ReactNode }) {
  return (
    <div className="mx-auto w-full max-w-[760px] px-6 py-12 sm:px-10">
      <Callout tone="danger">{children}</Callout>
    </div>
  );
}

export function BrokenRecordCallout({ path, message }: { path: string; message: string }) {
  return (
    <Callout tone="danger">
      <p className="font-medium">This file could not be read as a record.</p>
      <p className="mt-1 break-all font-mono text-xs opacity-90">{path}</p>
      <p className="mt-1">{message}</p>
    </Callout>
  );
}

export function LineageCalloutRow({ text, compareHref }: { text: string; compareHref: string }) {
  return (
    <Callout tone="lineage" icon={<GitCompare size={16} />}>
      <span>{text}</span>{" "}
      <Link
        to={compareHref}
        className="font-medium text-(--color-accent-text) underline decoration-1 underline-offset-[3px] hover:decoration-2"
      >
        Compare
      </Link>
    </Callout>
  );
}
