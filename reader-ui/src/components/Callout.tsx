import type { ReactNode } from "react";
import { AlertTriangle, Info, GitCompare } from "lucide-react";
import { Link } from "react-router";

type Tone = "neutral" | "danger" | "lineage";

const TONE_CLASSES: Record<Tone, string> = {
  neutral: "border-(--color-border) bg-(--color-bg-hover) text-(--color-text-muted)",
  danger: "border-(--color-accent-red-bg) bg-(--color-accent-red-bg) text-(--color-accent-red-text)",
  lineage: "border-(--color-border) bg-(--color-bg-raised) text-(--color-text)",
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
    <div className={`mb-6 flex items-start gap-2.5 rounded-lg border px-4 py-3 text-sm ${TONE_CLASSES[tone]}`}>
      <div className="mt-0.5 shrink-0">{icon ?? defaultIcon}</div>
      <div className="min-w-0">{children}</div>
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
      <Link to={compareHref} className="font-medium underline underline-offset-2">
        Compare
      </Link>
    </Callout>
  );
}
