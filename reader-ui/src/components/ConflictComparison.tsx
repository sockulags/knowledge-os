import { useEffect, useMemo, useRef } from "react";
import { AlertTriangle } from "lucide-react";
import { lineDiff, type DiffLine } from "../lib/lineDiff";

const LINE_CLASSES: Record<DiffLine["kind"], string> = {
  equal: "",
  removed: "bg-(--color-accent-red-bg) text-(--color-accent-red-text) shadow-[inset_2px_0_0_var(--color-accent-red-text)]",
  added: "bg-(--color-accent-green-bg) text-(--color-accent-green-text) shadow-[inset_2px_0_0_var(--color-accent-green-text)]",
};

function Side({ heading, lines, marker }: { heading: string; lines: DiffLine[]; marker: string }) {
  return (
    <div className="min-w-0">
      <h3 className="mb-2 text-[13px] font-medium text-(--color-text-muted)">{heading}</h3>
      <div className="kos-card max-h-[420px] overflow-auto py-2 font-mono text-xs leading-relaxed text-(--color-text)">
        {lines.map((line, index) => (
          <div key={index} className={`whitespace-pre-wrap break-words px-3 ${LINE_CLASSES[line.kind]}`}>
            {line.kind !== "equal" && <span className="sr-only">{marker} </span>}
            {line.text || " "}
          </div>
        ))}
      </div>
    </div>
  );
}

/** A write refused because the page changed on disk after it was opened:
 * the version now on disk next to the text being edited (stacked on narrow
 * screens), and the two ways forward. `changedFields` names the properties
 * (title, tags, ...) that also differ. */
export function ConflictComparison({
  theirs,
  mine,
  changedFields,
  keepMineBlocked,
  onKeepMine,
  onTakeTheirs,
}: {
  theirs: string;
  mine: string;
  changedFields: string[];
  /** Why "keep mine" cannot be sent yet, if it cannot. */
  keepMineBlocked: string | null;
  onKeepMine: () => void;
  onTakeTheirs: () => void;
}) {
  const panel = useRef<HTMLElement>(null);
  useEffect(() => panel.current?.focus(), []);
  const lines = useMemo(() => lineDiff(theirs, mine), [theirs, mine]);
  const current = lines.filter((line) => line.kind !== "added");
  const yours = lines.filter((line) => line.kind !== "removed");
  const sameText = lines.every((line) => line.kind === "equal");

  return (
    <section
      ref={panel}
      tabIndex={-1}
      aria-labelledby="conflict-heading"
      className="mb-6 rounded-(--radius-card) border border-[color-mix(in_srgb,var(--color-accent-red-text)_28%,transparent)] bg-(--color-bg) px-4 py-4 text-sm leading-relaxed text-(--color-text) outline-none focus-visible:ring-2 focus-visible:ring-(--color-accent)"
    >
      <h2 id="conflict-heading" className="flex items-center gap-2 font-medium text-(--color-accent-red-text)">
        <AlertTriangle size={16} aria-hidden="true" />
        This page changed while you were editing
      </h2>
      <p className="mt-1 text-(--color-text-muted)">
        Nothing was saved. Someone else (or the agent) wrote a newer version. Compare it with your text, then keep
        yours on top of it or take theirs. You can keep editing your text below meanwhile.
      </p>
      {changedFields.length > 0 && (
        <p className="mt-2 text-(--color-text-muted)">Properties that also differ: {changedFields.join(", ")}.</p>
      )}

      {sameText ? (
        <p className="mt-3 text-(--color-text-muted)">The page text is the same in both.</p>
      ) : (
        <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Side heading="Current version" lines={current} marker="Only in the current version:" />
          <Side heading="Your text" lines={yours} marker="Only in your text:" />
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={onKeepMine}
          disabled={keepMineBlocked !== null}
          className="kos-btn kos-btn-primary"
        >
          Keep mine on top of the new version
        </button>
        <button type="button" onClick={onTakeTheirs} className="kos-btn kos-btn-secondary">
          Take theirs
        </button>
        {keepMineBlocked && <span className="text-(--color-text-muted)">{keepMineBlocked}</span>}
      </div>
    </section>
  );
}
