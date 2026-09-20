import { useParams, Link } from "react-router";
import { api } from "../api/client";
import { useApi } from "../hooks/useApi";
import { PageSkeleton } from "../components/Skeleton";
import { EmptyState } from "../components/EmptyState";
import { Callout } from "../components/Callout";
import { Pill } from "../components/Pill";
import type { Comparison, DiffBlock } from "../api/types";

const BLOCK_CLASSES: Record<DiffBlock["kind"], string> = {
  equal: "",
  added: "bg-(--color-accent-green-bg) rounded px-2 -mx-2",
  removed: "bg-(--color-accent-red-bg) rounded px-2 -mx-2",
  changed: "bg-(--color-accent-yellow-bg) rounded px-2 -mx-2",
};

function ComparisonBlock({ comparison }: { comparison: Comparison }) {
  if (comparison.state !== "ok") {
    return (
      <section className="mt-8">
        <h2 className="mb-2 text-lg font-semibold">{comparison.heading}</h2>
        <Callout tone="neutral">{comparison.detail}</Callout>
      </section>
    );
  }
  return (
    <section className="mt-10">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-lg font-semibold">{comparison.heading}</h2>
        {comparison.summary && <p className="text-sm text-(--color-text-muted)">{comparison.summary}</p>}
      </div>
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
        <div>
          <div className="mb-2 flex items-center gap-2">
            <Pill pill={comparison.left?.status_pill} />
            <span className="truncate font-medium">{comparison.left?.title}</span>
          </div>
          <div className="space-y-3 rounded-lg border border-(--color-border) bg-(--color-bg-raised) p-4">
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
          <div className="space-y-3 rounded-lg border border-(--color-border) bg-(--color-bg-raised) p-4">
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
  const { data, loading, notFound, error } = useApi(() => api.compare(recordId!), [recordId]);

  if (loading) return <PageSkeleton />;
  if (notFound)
    return <EmptyState title="Record not found" body={`No record with id "${recordId}" exists in this workspace.`} />;
  if (error || !data) return <Callout tone="danger">{error ?? "Could not load this comparison."}</Callout>;

  return (
    <div className="mx-auto w-full max-w-[900px] px-6 py-12 sm:px-10">
      <p className="text-sm text-(--color-text-muted)">
        <Link to={`/r/${data.record.id}`} className="hover:underline">
          {data.record.title}
        </Link>
      </p>
      <h1 className="text-[26px] sm:text-[32px] font-semibold leading-tight tracking-tight">Compare</h1>
      <p className="mt-1 text-(--color-text-muted)">{data.status_text}</p>

      {data.comparisons.length === 0 ? (
        <div className="mt-8">
          <EmptyState
            title="Nothing to compare"
            body={data.no_comparison_text}
            action={
              <Link
                to={`/r/${data.record.id}`}
                className="mt-2 rounded-md border border-(--color-border) px-3 py-1.5 text-sm hover:bg-(--color-bg-hover)"
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
