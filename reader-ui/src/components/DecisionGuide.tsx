import { useState } from "react";
import { ArrowRight, CornerDownRight, HelpCircle } from "lucide-react";
import type { DecisionLanguage, Tone } from "../api/types";
import { Pill } from "./Pill";

type StateKey = DecisionLanguage["guide"]["states"][number]["key"];

const STATE_TONES: Record<StateKey, Tone> = {
  proposed: "amber",
  in_force: "green",
  replaced: "grey",
  withdrawn: "grey",
};

/** The lifecycle as a small picture: Proposed -> In force -> Replaced, with
 * Withdrawn branching off Proposed. */
function StateFlow({ guide }: { guide: DecisionLanguage["guide"] }) {
  const byKey = Object.fromEntries(guide.states.map((state) => [state.key, state])) as Record<
    StateKey,
    DecisionLanguage["guide"]["states"][number]
  >;
  const pill = (key: StateKey) => <Pill pill={{ label: byKey[key].label, tone: STATE_TONES[key] }} />;
  return (
    <div className="my-4 inline-flex flex-col gap-2" aria-hidden="true">
      <div className="flex flex-wrap items-center gap-2">
        {pill("proposed")}
        <ArrowRight size={14} className="text-(--color-text-faint)" />
        {pill("in_force")}
        <ArrowRight size={14} className="text-(--color-text-faint)" />
        {pill("replaced")}
      </div>
      <div className="flex items-center gap-2 pl-4">
        <CornerDownRight size={14} className="text-(--color-text-faint)" />
        {pill("withdrawn")}
      </div>
    </div>
  );
}

/** "How decisions work": a few sentences, the states as a picture, and one
 * line per state. */
export function DecisionGuidePanel({ language, showTitle = true }: { language: DecisionLanguage; showTitle?: boolean }) {
  const { guide } = language;
  return (
    <div className="kos-card px-5 py-4 text-sm leading-relaxed" role="region" aria-label={guide.title}>
      {showTitle && <p className="kos-heading mb-1 text-[17px]">{guide.title}</p>}
      <p className="text-(--color-text-muted)">{guide.intro}</p>
      <StateFlow guide={guide} />
      <dl className="space-y-1.5">
        {guide.states.map((state) => (
          <div key={state.key} className="grid grid-cols-[96px_1fr] gap-3">
            <dt className="font-medium text-(--color-text)">{state.label}</dt>
            <dd className="text-(--color-text-muted)">{state.text}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-3 text-(--color-text-muted)">{guide.undo}</p>
    </div>
  );
}

/** A "How decisions work" link that opens the guide in place. */
export function DecisionGuideToggle({ language, defaultOpen = false }: { language: DecisionLanguage; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="-mx-1 flex items-center gap-1.5 rounded-(--radius-control) px-1 text-sm text-(--color-text-muted) underline-offset-[3px] hover:text-(--color-accent-text) hover:underline"
      >
        <HelpCircle size={14} />
        {language.labels.how_it_works}
      </button>
      {open && (
        <div className="mt-3">
          <DecisionGuidePanel language={language} showTitle={false} />
        </div>
      )}
    </div>
  );
}
