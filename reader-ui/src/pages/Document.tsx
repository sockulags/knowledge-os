import { useState } from "react";
import { useParams, Link } from "react-router";
import { AlertTriangle, FilePlus, Pencil } from "lucide-react";
import { api } from "../api/client";
import { useApi } from "../hooks/useApi";
import { PageSkeleton } from "../components/Skeleton";
import { Breadcrumb } from "../components/Breadcrumb";
import { PropertiesBlock } from "../components/PropertiesBlock";
import { TechnicalDetails } from "../components/TechnicalDetails";
import { Markdown } from "../components/Markdown";
import { TableOfContents } from "../components/TableOfContents";
import { EmptyState } from "../components/EmptyState";
import { Callout, LineageCalloutRow } from "../components/Callout";
import { DecisionActions } from "../components/DecisionActions";
import { useShell } from "../components/Shell";
import type { RelationView } from "../api/types";

function RelationRow({ relation }: { relation: RelationView }) {
  if (!relation.resolved) {
    return (
      <div className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm text-(--color-text-faint)">
        <AlertTriangle size={14} />
        {relation.label}
      </div>
    );
  }
  return (
    <Link to={relation.href!} className="block rounded-md px-2 py-1.5 text-sm hover:bg-(--color-bg-hover)">
      {relation.label}
    </Link>
  );
}

export function Document() {
  const { recordId } = useParams<{ recordId: string }>();
  const { refreshNav } = useShell();
  // Bumped after a decision action so the page shows the new state.
  const [loadKey, setLoadKey] = useState(0);
  const { data, loading, notFound, error } = useApi(() => api.record(recordId!), [recordId, loadKey]);

  if (loading) return <PageSkeleton />;
  if (notFound)
    return <EmptyState title="Record not found" body={`No record with id "${recordId}" exists in this workspace.`} />;
  if (error || !data) return <Callout tone="danger">{error ?? "Could not load this record."}</Callout>;

  const showToc = data.headings.length >= 3;

  return (
    <div className="mx-auto flex w-full max-w-[1100px] gap-10 px-6 py-12 sm:px-10">
      <div className="mx-auto w-full max-w-[720px]">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <Breadcrumb items={data.breadcrumb} current={data.title} />
          <div className="no-print ml-auto flex items-center gap-1">
            {data.editing.project_id && (
              <Link
                to={`/p/${data.editing.project_id}/new${data.editing.folder ? `?folder=${encodeURIComponent(data.editing.folder)}` : ""}`}
                className="flex items-center gap-1.5 rounded-md px-2 py-1 text-sm text-(--color-text-muted) hover:bg-(--color-bg-hover) hover:text-(--color-text)"
              >
                <FilePlus size={14} />
                New page here
              </Link>
            )}
            {data.editing.editable && (
              <Link
                to={`/r/${data.id}/edit`}
                className="flex items-center gap-1.5 rounded-md px-2 py-1 text-sm text-(--color-text-muted) hover:bg-(--color-bg-hover) hover:text-(--color-text)"
              >
                <Pencil size={14} />
                Edit
              </Link>
            )}
          </div>
        </div>
        <h1 className="text-[28px] sm:text-[36px] font-semibold leading-tight tracking-tight">{data.title}</h1>

        {data.lineage.map((callout, index) => (
          <div className="mt-6" key={index}>
            <LineageCalloutRow text={callout.text} compareHref={callout.compare_href} />
          </div>
        ))}

        <div className="mt-6">
          <PropertiesBlock properties={data.properties} />
        </div>
        <TechnicalDetails details={data.technical_details} />
        <DecisionActions
          record={data}
          onDone={() => {
            setLoadKey((value) => value + 1);
            refreshNav();
          }}
        />

        <Markdown html={data.body_html} />

        {(data.inbound.length > 0 || data.outbound.length > 0) && (
          <div className="mt-12 grid grid-cols-1 gap-8 border-t border-(--color-border) pt-8 sm:grid-cols-2">
            <section>
              <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-(--color-text-faint)">
                Linked from
              </h3>
              {data.inbound.length === 0 ? (
                <p className="text-sm text-(--color-text-faint)">Nothing links here yet.</p>
              ) : (
                <div className="space-y-0.5">
                  {data.inbound.map((relation, index) => (
                    <RelationRow key={index} relation={relation} />
                  ))}
                </div>
              )}
            </section>
            <section>
              <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-(--color-text-faint)">
                Links to
              </h3>
              {data.outbound.length === 0 ? (
                <p className="text-sm text-(--color-text-faint)">This record points at nothing else.</p>
              ) : (
                <div className="space-y-0.5">
                  {data.outbound.map((relation, index) => (
                    <RelationRow key={index} relation={relation} />
                  ))}
                </div>
              )}
            </section>
          </div>
        )}
      </div>
      {showToc && <TableOfContents headings={data.headings} />}
    </div>
  );
}
