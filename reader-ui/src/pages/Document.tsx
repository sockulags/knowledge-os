import { useCallback, useRef, useState } from "react";
import { useParams, Link } from "react-router";
import { AlertTriangle, FilePlus, Pencil, Trash2 } from "lucide-react";
import { api } from "../api/client";
import { useApi } from "../hooks/useApi";
import { PageSkeleton } from "../components/Skeleton";
import { Breadcrumb } from "../components/Breadcrumb";
import { PropertiesBlock } from "../components/PropertiesBlock";
import { TechnicalDetails } from "../components/TechnicalDetails";
import { Markdown } from "../components/Markdown";
import { TableOfContents } from "../components/TableOfContents";
import { RecordNotFound } from "../components/EmptyState";
import { LoadError, LineageCalloutRow } from "../components/Callout";
import { DecisionActions } from "../components/DecisionActions";
import { useShell } from "../components/Shell";
import { useStructure, type TreeItem } from "../components/Structure";
import { showsOutcome } from "../lib/pendingActions";
import { decisionKey, pendingActions, useOnPendingSettled, usePendingEntries } from "../lib/pendingStore";
import { loadErrorMessage } from "../lib/language";
import { useDocumentTitle } from "../hooks/useDocumentTitle";
import type { RelationView } from "../api/types";

function RelationRow({ relation }: { relation: RelationView }) {
  if (!relation.resolved) {
    return (
      <div className="flex items-center gap-2 rounded-(--radius-control) px-2 py-1.5 text-sm text-(--color-text-faint)">
        <AlertTriangle size={14} />
        {relation.label}
      </div>
    );
  }
  return (
    <Link to={relation.href!} className="kos-row px-2 py-1.5 text-sm">
      {relation.label}
    </Link>
  );
}

export function Document() {
  const { recordId } = useParams<{ recordId: string }>();
  const { nav } = useShell();
  const structure = useStructure();
  // Bumped after a decision action was saved (or failed) so the page shows
  // what the core now holds.
  const [loadKey, setLoadKey] = useState(0);
  const loadedAt = useRef(0);
  const apiState = useApi(() => {
    loadedAt.current = Date.now();
    return api.record(recordId!);
  }, [recordId, loadKey]);
  const { data, loading, notFound } = apiState;
  useDocumentTitle(nav?.workspace_name, data?.title ?? null);

  // A decision action on this page shows its outcome from the click on,
  // while the write waits for Undo, and until the page has reloaded.
  const entries = usePendingEntries();
  const key = recordId ? decisionKey(recordId) : "";
  const pending = entries.find((entry) => entry.key === key && showsOutcome(entry, loadedAt.current)) ?? null;
  useOnPendingSettled(
    useCallback(() => {
      const entry = pendingActions.entry(key);
      if (entry !== null && entry.settledAt !== null && entry.settledAt > loadedAt.current) {
        setLoadKey((value) => value + 1);
      }
    }, [key]),
  );

  if (loading) return <PageSkeleton />;
  if (notFound) return <RecordNotFound nav={nav} recordId={recordId} />;
  if (apiState.error || !data)
    return <LoadError>{loadErrorMessage(apiState, nav?.language, "Could not load this page.")}</LoadError>;

  const showToc = data.headings.length >= 3;
  const properties = pending ? { ...data.properties, status: pending.meta.outcome.status } : data.properties;
  const deletion = data.editing.delete;
  const deleteItem: TreeItem | null =
    deletion === null
      ? null
      : deletion.kind === "folder"
        ? { kind: "folder", projectId: deletion.project_id, path: deletion.path, title: data.title, hasPage: true }
        : { kind: "page", id: data.id, title: data.title, projectId: data.editing.project_id ?? "", folder: data.editing.folder };

  return (
    <div className="mx-auto flex w-full max-w-[1100px] gap-10 px-6 py-12 sm:px-10">
      <div className="mx-auto w-full max-w-[720px]">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <Breadcrumb items={data.breadcrumb} current={data.title} />
          <div className="no-print ml-auto flex items-center gap-1">
            {data.editing.project_id && (
              <Link
                to={`/p/${data.editing.project_id}/new${data.editing.folder ? `?folder=${encodeURIComponent(data.editing.folder)}` : ""}`}
                className="kos-btn kos-btn-ghost kos-btn-sm"
              >
                <FilePlus size={14} />
                New page here
              </Link>
            )}
            {data.editing.editable && (
              <Link
                to={`/r/${data.id}/edit`}
                className="kos-btn kos-btn-ghost kos-btn-sm"
              >
                <Pencil size={14} />
                Edit
              </Link>
            )}
            {deleteItem !== null && (
              <button type="button" className="kos-btn kos-btn-ghost kos-btn-sm" onClick={() => structure.remove(deleteItem)}>
                <Trash2 size={14} />
                Delete…
              </button>
            )}
          </div>
        </div>
        <h1 className="kos-title">{data.title}</h1>

        {data.lineage.map((callout, index) => (
          <div className="mt-6" key={index}>
            <LineageCalloutRow text={callout.text} compareHref={callout.compare_href} />
          </div>
        ))}

        <div className="mt-6">
          <PropertiesBlock properties={properties} />
        </div>
        <TechnicalDetails details={data.technical_details} />
        {data.decision_language && data.editing.decision_actions && (
          <DecisionActions
            target={{
              id: data.id,
              title: data.title,
              content_sha256: data.editing.content_sha256,
              actions: data.editing.decision_actions,
              project_id: data.editing.project_id,
              folder: data.editing.folder,
            }}
            language={data.decision_language}
            pending={pending}
          />
        )}

        <Markdown html={data.body_html} />

        {(data.inbound.length > 0 || data.outbound.length > 0) && (
          <div className="mt-14 grid grid-cols-1 gap-8 border-t border-(--color-border) pt-8 sm:grid-cols-2">
            <section>
              <h3 className="kos-eyebrow mb-2.5">
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
              <h3 className="kos-eyebrow mb-2.5">
                Links to
              </h3>
              {data.outbound.length === 0 ? (
                <p className="text-sm text-(--color-text-faint)">This page links to nothing else.</p>
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
