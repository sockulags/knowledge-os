import { Fragment, type ReactNode } from "react";
import type { DecisionLanguage, Tone } from "../api/types";

export interface LifecycleStage {
  key: string;
  label: string;
  tone: Tone;
}

/** One step along the line. Several stages in one step are alternative
 * endings (replaced or withdrawn), drawn side by side. */
export type LifecycleStep = LifecycleStage[];

export interface Lifecycle {
  steps: LifecycleStep[];
  current: string;
}

const TONE_CLASSES: Record<string, string> = {
  green: "bg-(--color-accent-green-bg) text-(--color-accent-green-text)",
  amber: "bg-(--color-accent-amber-bg) text-(--color-accent-amber-text)",
  yellow: "bg-(--color-accent-yellow-bg) text-(--color-accent-yellow-text)",
  grey: "bg-(--color-accent-grey-bg) text-(--color-accent-grey-text)",
  violet: "bg-(--color-accent-violet-bg) text-(--color-accent-violet-text)",
};

type DecisionStateKey = DecisionLanguage["guide"]["states"][number]["key"];

const DECISION_STATES: Record<string, DecisionStateKey> = {
  draft: "proposed",
  active: "in_force",
  superseded: "replaced",
  archived: "withdrawn",
};

const DECISION_FALLBACK: Record<DecisionStateKey, string> = {
  proposed: "Proposed",
  in_force: "In force",
  replaced: "Replaced",
  withdrawn: "Withdrawn",
};

/** A decision's lifecycle, in the words of the "How decisions work" guide:
 * Proposed, In force, then Replaced or Withdrawn. Null for a status the
 * lifecycle does not draw. */
export function decisionLifecycle(language: DecisionLanguage | null | undefined, status: string): Lifecycle | null {
  const current = DECISION_STATES[status];
  if (!current) return null;
  const labels = Object.fromEntries((language?.guide?.states ?? []).map((state) => [state.key, state.label]));
  const stage = (key: DecisionStateKey, tone: Tone): LifecycleStage => ({
    key,
    label: labels[key] ?? DECISION_FALLBACK[key],
    tone,
  });
  return {
    steps: [[stage("proposed", "amber")], [stage("in_force", "green")], [stage("replaced", "grey"), stage("withdrawn", "grey")]],
    current,
  };
}

/** A page that is not a decision: Draft, Current, then Replaced or Archived
 * (or Discouraged, shown only when the page is). */
export function recordLifecycle(status: string): Lifecycle | null {
  const ends: LifecycleStage[] = [
    { key: "superseded", label: "Replaced", tone: "grey" },
    { key: "archived", label: "Archived", tone: "grey" },
  ];
  if (status === "deprecated") ends.unshift({ key: "deprecated", label: "Discouraged", tone: "grey" });
  const steps: LifecycleStep[] = [
    [{ key: "draft", label: "Draft", tone: "amber" }],
    [{ key: "active", label: "Current", tone: "green" }],
    ends,
  ];
  if (!steps.some((step) => step.some((stage) => stage.key === status))) return null;
  return { steps, current: status };
}

/** A proposed page change waiting in Decide: Proposed, then Accepted or
 * Discarded. */
export function changeLifecycle(): Lifecycle {
  return {
    steps: [
      [{ key: "proposed", label: "Proposed", tone: "amber" }],
      [
        { key: "accepted", label: "Accepted", tone: "green" },
        { key: "discarded", label: "Discarded", tone: "grey" },
      ],
    ],
    current: "proposed",
  };
}

/** The sentence a screen reader hears for the strip. */
export function lifecycleDescription(lifecycle: Lifecycle, name = "Lifecycle"): string {
  const parts = lifecycle.steps.map((step) =>
    step.map((stage) => (stage.key === lifecycle.current ? `${stage.label} (now)` : stage.label)).join(" or "),
  );
  return `${name}: ${parts.join(", then ")}`;
}

/** Where an item stands in its lifecycle, as one line: a dot and a label per
 * stage joined by short rules, the current stage tinted in its status
 * colour, the stages behind it solid and the ones ahead hollow. The visible
 * labels stay; assistive technology hears the same in one sentence. */
export function LifecycleStrip({
  lifecycle,
  name,
  note,
  className = "",
}: {
  lifecycle: Lifecycle;
  name?: string;
  /** Text after the strip, such as the review rule that holds a proposal. */
  note?: ReactNode;
  className?: string;
}) {
  const currentIndex = lifecycle.steps.findIndex((step) => step.some((stage) => stage.key === lifecycle.current));
  return (
    <div className={`flex flex-wrap items-center gap-x-3 gap-y-1 text-xs ${className}`}>
      <div
        role="img"
        aria-label={lifecycleDescription(lifecycle, name)}
        data-stage={lifecycle.current}
        className="inline-flex flex-wrap items-center gap-x-1.5 gap-y-1"
      >
        {lifecycle.steps.map((step, index) => (
          <Fragment key={step.map((stage) => stage.key).join("|")}>
            {index > 0 && (
              <span
                aria-hidden="true"
                className={`h-px w-4 shrink-0 ${
                  index <= currentIndex ? "bg-(--color-text-faint)" : "bg-(--color-border-strong)"
                }`}
              />
            )}
            <span className="inline-flex items-center gap-1">
              {step.map((stage, alt) => {
                const place =
                  stage.key === lifecycle.current ? "current" : index < currentIndex ? "past" : index > currentIndex ? "ahead" : "other";
                return (
                  <Fragment key={stage.key}>
                    {alt > 0 && <span className="text-(--color-text-faint)">/</span>}
                    <Stage stage={stage} place={place} />
                  </Fragment>
                );
              })}
            </span>
          </Fragment>
        ))}
      </div>
      {note && <span className="text-(--color-text-faint)">{note}</span>}
    </div>
  );
}

function Stage({ stage, place }: { stage: LifecycleStage; place: "current" | "past" | "ahead" | "other" }) {
  if (place === "current") {
    const tone = (stage.tone && TONE_CLASSES[stage.tone]) || "bg-(--color-bg-hover) text-(--color-text)";
    return (
      <span
        data-current="true"
        className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-[5px] px-1.5 py-[3px] font-medium leading-none ${tone}`}
      >
        <span className="h-1.5 w-1.5 rounded-full bg-current" />
        {stage.label}
      </span>
    );
  }
  // Behind: a solid dot. Ahead (or the ending not taken): a hollow one.
  const dot =
    place === "past"
      ? "bg-(--color-text-faint)"
      : "border border-(--color-border-strong) bg-transparent";
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap px-0.5 py-[3px] leading-none text-(--color-text-faint)">
      <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />
      {stage.label}
    </span>
  );
}
