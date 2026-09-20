import type { Pill as PillData } from "../api/types";

const TONE_CLASSES: Record<string, string> = {
  green: "bg-(--color-accent-green-bg) text-(--color-accent-green-text)",
  amber: "bg-(--color-accent-amber-bg) text-(--color-accent-amber-text)",
  yellow: "bg-(--color-accent-yellow-bg) text-(--color-accent-yellow-text)",
  grey: "bg-(--color-accent-grey-bg) text-(--color-accent-grey-text)",
  violet: "bg-(--color-accent-violet-bg) text-(--color-accent-violet-text)",
};

export function Pill({ pill }: { pill: PillData | null | undefined }) {
  if (!pill) return null;
  const toneClass = (pill.tone && TONE_CLASSES[pill.tone]) || "bg-(--color-bg-hover) text-(--color-text-muted)";
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium leading-none ${toneClass}`}
    >
      {pill.label}
    </span>
  );
}
