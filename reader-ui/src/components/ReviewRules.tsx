import { useEffect, useState, type ReactNode } from "react";
import { ChevronRight, ShieldCheck } from "lucide-react";
import { api } from "../api/client";
import type { ReviewRulesPayload } from "../api/types";

/** The rules are read once per app load and shared by every place that shows them. */
let loading: Promise<ReviewRulesPayload> | null = null;

function loadRules(): Promise<ReviewRulesPayload> {
  if (loading === null) {
    loading = api.reviewRules().catch((error: unknown) => {
      loading = null; // a failed read is tried again next time
      throw error;
    });
  }
  return loading;
}

/** For tests: read the rules again on the next mount. */
export function forgetReviewRules() {
  loading = null;
}

function useReviewRules(): ReviewRulesPayload | null {
  const [rules, setRules] = useState<ReviewRulesPayload | null>(null);
  useEffect(() => {
    let current = true;
    loadRules().then(
      (payload) => current && setRules(payload),
      () => undefined, // nothing to show; the rest of the page does not wait for this
    );
    return () => {
      current = false;
    };
  }, []);
  return rules;
}

export const NO_RULES = "No review rules: agent and person writes land directly.";
const SNIPPET = '[[review.rule]]\nwriter = "agent"\naction = "review"';

function countLabel(count: number): string {
  return count === 1 ? "1 review rule applies." : `${count} review rules apply.`;
}

/** A one-line toggle that shows its children below it. */
function Disclosure({ label, className, children }: { label: string; className: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className={`flex items-center gap-1 text-left hover:text-(--color-text) ${className}`}
      >
        <ChevronRight size={12} className={open ? "rotate-90 transition-transform duration-100" : "transition-transform duration-100"} />
        {label}
      </button>
      {open && <div className="mt-1.5">{children}</div>}
    </>
  );
}

function RuleList({ payload }: { payload: ReviewRulesPayload }) {
  if (payload.rules.length === 0) return null;
  return (
    <>
      <ol className="space-y-1" aria-label="Review rules">
        {payload.rules.map((rule) => (
          <li key={rule.number} className="text-(--color-text)">
            {rule.description}
          </li>
        ))}
      </ol>
      <p className="mt-1.5 text-(--color-text-faint)">
        The first rule that matches a write decides; a write no rule matches lands directly.
      </p>
    </>
  );
}

function HowToAdd({ none }: { none: boolean }) {
  return (
    <>
      <p className="text-(--color-text-muted)">
        {none ? "To hold agent notes for review in Decide" : "To add a rule"}, add this to knowledge-os.toml (a rule
        can also name project, folder, and writes):
      </p>
      <pre className="mt-1 overflow-x-auto rounded-[5px] bg-(--color-bg-sidebar) px-2 py-1.5 font-mono text-xs text-(--color-text)">
        {SNIPPET}
      </pre>
    </>
  );
}

/**
 * Which review rules apply: which writes wait for a person in Decide and
 * which land directly. Shown in Decide (`variant="full"`) and under the agent
 * panel's header (`variant="compact"`, one line that opens the details). Shows
 * nothing until the rules are read, so nothing waits on it.
 */
export function ReviewRules({ variant }: { variant: "full" | "compact" }) {
  const payload = useReviewRules();
  if (payload === null) return null;
  const none = payload.rules.length === 0;

  if (variant === "full") {
    // Decide already shows a broken rule file as an error of its own.
    if (payload.error !== null) return null;
    return (
      <section className="mt-6 text-sm" aria-label="Review rules" data-testid="review-rules">
        <h2 className="flex items-center gap-1.5 text-[13px] font-medium text-(--color-text-muted)">
          <ShieldCheck size={14} />
          {none ? NO_RULES : countLabel(payload.rules.length)}
        </h2>
        {!none && (
          <div className="mt-2">
            <RuleList payload={payload} />
          </div>
        )}
        <div className="mt-1.5 text-xs">
          <Disclosure label={none ? "How to add a rule" : "How to add another rule"} className="text-(--color-text-faint)">
            <HowToAdd none={none} />
          </Disclosure>
        </div>
      </section>
    );
  }

  const broken = payload.error !== null;
  return (
    <div className="border-b border-(--color-border) px-3 py-1.5 text-xs" data-testid="review-rules">
      <Disclosure
        label={broken ? "The review rules cannot be used." : none ? NO_RULES : countLabel(payload.rules.length)}
        className={`w-full ${broken ? "text-(--color-accent-red-text)" : "text-(--color-text-faint)"}`}
      >
        <div className="pb-1">
          {broken ? (
            <p className="text-(--color-accent-red-text)">The writes they govern are refused: {payload.error}</p>
          ) : (
            <>
              <RuleList payload={payload} />
              <div className={none ? "" : "mt-2"}>
                <HowToAdd none={none} />
              </div>
            </>
          )}
        </div>
      </Disclosure>
    </div>
  );
}
