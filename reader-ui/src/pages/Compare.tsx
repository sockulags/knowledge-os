import { useParams, Link } from "react-router";
import { api } from "../api/client";
import { useApi } from "../hooks/useApi";
import { PageSkeleton } from "../components/Skeleton";
import { EmptyState, RecordNotFound } from "../components/EmptyState";
import { Callout, LoadError } from "../components/Callout";
import { Pill } from "../components/Pill";
import { useShell } from "../components/Shell";
import { loadErrorMessage } from "../lib/language";
import type { Comparison, DiffBlock } from "../api/types";

const BLOCK_CLASSES: Record<DiffBlock["kind"], string> = {
  equal: "",
  added: "bg-(--color-accent-green-bg) rounded-(--radius-control) px-2 -mx-2 shadow-[inset_2px_0_0_var(--color-accent-green-text)]",
  removed: "bg-(--color-accent-red-bg) rounded-(--radius-control) px-2 -mx-2 shadow-[inset_2px_0_0_var(--color-accent-red-text)]",
  // A "changed" paragraph carries no fill of its own -- an amber left rule
  // marks it as "this one differs", while the words that actually moved
  // get the fill (via [&_mark]) instead. Tinting the *whole* paragraph the
  // same flat colour as every other changed paragraph made a one-word edit
  // and a full rewrite look identical; putting the colour only on what
  // changed is what actually answers "what changed" at a glance.
  changed:
    "border-l-2 border-(--color-accent-amber-text) pl-3 [&_mark]:bg-(--color-accent-amber-bg) [&_mark]:text-(--color-accent-amber-text) [&_mark]:rounded [&_mark]:px-0.5 [&_mark]:not-italic [&_mark]:font-medium",
};

function ComparisonBlock({ comparison }: { comparison: Comparison }) {
  if (comparison.state !== "ok") {
    return (
      <section className="mt-8">
        <h2 className="kos-heading mb-3">{comparison.heading}</h2>
        <Callout tone="neutral">{comparison.detail}</Callout>
      </section>
    );
  }
  return (
    <section className="mt-10">
      <div className="mb-3 flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <h2 className="kos-heading">{comparison.heading}</h2>
        {comparison.summary && <p className="text-sm text-(--color-text-muted)">{comparison.summary}</p>}
      </div>
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
        <div>
          <div className="mb-2 flex items-center gap-2">
            <Pill pill={comparison.left?.status_pill} />
            <span className="truncate font-medium">{comparison.left?.title}</span>
          </div>
          <div className="kos-card space-y-3 p-5">
            {comparison.blocks.map((block, index) => (
              <div key={index} className={`prose prose-kos prose-sm max-w-none ${BLOCK_CLASSES[block.kind]}`}>
                {block.left_html ? (
                  <div dangerouslySetInnerHTML={{ __html: block.left_html }} />
                ) : (
                  <p className="text-sm italic text-(--color-text-faint)">Not present.</p>
                )}
              </div>
            ))}
          </div>
        </div>
        <div>
          <div className="mb-2 flex items-center gap-2">
            <Pill pill={comparison.right?.status_pill} />
            <span className="truncate font-medium">{comparison.right?.title}</span>
          </div>
          <div className="kos-card space-y-3 p-5">
            {comparison.blocks.map((block, index) => (
              <div key={index} className={`prose prose-kos prose-sm max-w-none ${BLOCK_CLASSES[block.kind]}`}>
                {block.right_html ? (
                  <div dangerouslySetInnerHTML={{ __html: block.right_html }} />
                ) : (
                  <p className="text-sm italic text-(--color-text-faint)">Not present.</p>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

export function Compare() {
  const { recordId } = useParams<{ recordId: string }>();
  const { nav } = useShell();
  const apiState = useApi(() => api.compare(recordId!), [recordId]);
  const { data, loading, notFound } = apiState;

  if (loading) return <PageSkeleton />;
  if (notFound) return <RecordNotFound nav={nav} recordId={recordId} />;
  if (apiState.error || !data)
    return <LoadError>{loadErrorMessage(apiState, nav?.language, "Could not load this comparison.")}</LoadError>;

  return (
    <div className="mx-auto w-full max-w-[900px] px-6 py-12 sm:px-10">
      <p className="mb-2 text-[13px] text-(--color-text-muted)">
        <Link to={`/r/${data.record.id}`} className="rounded-sm hover:text-(--color-text) hover:underline hover:underline-offset-[3px]">
          {data.record.title}
        </Link>
      </p>
      <h1 className="kos-title">Compare</h1>
      <p className="kos-lede">{data.status_text}</p>

      {data.comparisons.length === 0 ? (
        <div className="mt-8">
          <EmptyState
            title="Nothing to compare"
            body={data.no_comparison_text}
            action={
              <Link
                to={`/r/${data.record.id}`}
                className="kos-btn kos-btn-secondary mt-3"
              >
                Back to {data.record.title}
              </Link>
            }
          />
        </div>
      ) : (
        data.comparisons.map((comparison, index) => <ComparisonBlock key={index} comparison={comparison} />)
      )}
    </div>
  );
}
