import type { Pill as PillData } from "../api/types";

const TONE_CLASSES: Record<string, string> = {
  green: "bg-(--color-accent-green-bg) text-(--color-accent-green-text)",
  amber: "bg-(--color-accent-amber-bg) text-(--color-accent-amber-text)",
  yellow: "bg-(--color-accent-yellow-bg) text-(--color-accent-yellow-text)",
  grey: "bg-(--color-accent-grey-bg) text-(--color-accent-grey-text)",
  violet: "bg-(--color-accent-violet-bg) text-(--color-accent-violet-text)",
};

/** A status badge: a small tinted label with a dot in the same colour, so the
 * state still reads in greyscale and at a glance down a list. */
export function Pill({ pill }: { pill: PillData | null | undefined }) {
  if (!pill) return null;
  const toneClass = (pill.tone && TONE_CLASSES[pill.tone]) || "bg-(--color-bg-hover) text-(--color-text-muted)";
  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-[5px] px-1.5 py-[3px] text-xs font-medium leading-none ${toneClass}`}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden="true" />
      {pill.label}
    </span>
  );
}
