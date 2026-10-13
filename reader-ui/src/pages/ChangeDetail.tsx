import { useCallback, useState } from "react";
import { Link, useParams } from "react-router";
import { api } from "../api/client";
import type { ChangeDetail as ChangeDetailPayload } from "../api/types";
import { useApi } from "../hooks/useApi";
import { useDocumentTitle } from "../hooks/useDocumentTitle";
import { useShell } from "../components/Shell";
import { PageSkeleton } from "../components/Skeleton";
import { EmptyState } from "../components/EmptyState";
import { LoadError } from "../components/Callout";
import { Markdown } from "../components/Markdown";
import { ChangeActions, changeKey } from "../components/ChangeActions";
import { loadErrorMessage } from "../lib/language";
import { showsOutcome } from "../lib/pendingActions";
import { useOnPendingSettled, usePendingEntries } from "../lib/pendingStore";
import { BLOCK_CLASSES } from "./Compare";

function formatValue(value: unknown): string {
  if (value === null || value === undefined || (Array.isArray(value) && value.length === 0)) return "—";
  if (Array.isArray(value)) return value.join(", ");
  return String(value);
}

function Diff({ data }: { data: ChangeDetailPayload }) {
  const { labels } = data;
  return (
    <>
      {data.metadata_changes.length > 0 && (
        <section className="mt-8">
          <h2 className="kos-heading mb-3">{labels.metadata_heading}</h2>
          <dl className="kos-card divide-y divide-(--color-border) text-sm">
            {data.metadata_changes.map((change) => (
              <div key={change.field} className="grid grid-cols-[8rem_1fr] gap-3 px-5 py-2.5">
                <dt className="font-medium capitalize text-(--color-text-muted)">{change.field}</dt>
                <dd>
                  <span className="text-(--color-accent-red-text) line-through">{formatValue(change.before)}</span>{" "}
                  → <span className="text-(--color-accent-green-text)">{formatValue(change.after)}</span>
                </dd>
              </div>
            ))}
          </dl>
        </section>
      )}
      <section className="mt-8">
        <div className="mb-3 flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
          <h2 className="kos-heading">{labels.body_heading}</h2>
          {data.summary && <p className="text-sm text-(--color-text-muted)">{data.summary}</p>}
        </div>
        {data.blocks.every((block) => block.kind === "equal") ? (
          <p className="text-sm text-(--color-text-muted)">{labels.no_body_change}</p>
        ) : (
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
            {(["left_html", "right_html"] as const).map((side) => (
              <div key={side}>
                <p className="mb-2 text-[13px] font-medium text-(--color-text-muted)">
                  {side === "left_html" ? labels.current : labels.proposed}
                </p>
                <div className="kos-card space-y-3 p-5">
                {data.blocks.map((block, index) => (
                  <div key={index} className={`prose prose-kos prose-sm max-w-none ${BLOCK_CLASSES[block.kind]}`}>
                    {block[side] ? (
                      <div dangerouslySetInnerHTML={{ __html: block[side]! }} />
                    ) : (
                      <p className="text-sm italic text-(--color-text-faint)">Not present.</p>
                    )}
                  </div>
                ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </>
  );
}

/** One proposed change: what it would write, who proposed it and why it
 * waits, and Accept / Discard with Undo. */
export function ChangeDetail() {
  const { changeId } = useParams<{ changeId: string }>();
  const { nav } = useShell();
  const [loadedAt, setLoadedAt] = useState(() => Date.now());
  // Bumped when an action on this change has been saved, to load it again.
  const [version, setVersion] = useState(0);
  const apiState = useApi(() => {
    setLoadedAt(Date.now());
    return api.change(changeId!);
  }, [changeId, version]);
  const { data, loading, notFound } = apiState;
  const entries = usePendingEntries();
  useDocumentTitle(nav?.workspace_name, data ? `Proposed: ${data.title}` : null);
  const refresh = useCallback(() => setVersion((value) => value + 1), []);
  useOnPendingSettled(refresh);

  const pending = entries.find((entry) => entry.key === changeKey(changeId ?? "")) ?? null;
  if (loading && !data) return <PageSkeleton />;
  if (notFound || (pending === null && !data))
    return (
      <EmptyState
        title="This proposed change is gone"
        body="It was accepted or discarded. Accepted changes are in the knowledge base; the Decide inbox lists what still waits."
        action={
          <Link to="/decide" className="kos-btn kos-btn-secondary">
            Open Decide
          </Link>
        }
      />
    );
  if (apiState.error || !data)
    return <LoadError>{loadErrorMessage(apiState, nav?.language, "Could not load this proposed change.")}</LoadError>;

  const shownPending = pending !== null && showsOutcome(pending, loadedAt) ? pending : null;
  return (
    <div className="mx-auto w-full max-w-[900px] px-6 py-12 sm:px-10">
      <p className="mb-2 text-[13px] text-(--color-text-muted)">
        <Link to="/decide" className="rounded-sm hover:text-(--color-text) hover:underline hover:underline-offset-[3px]">
          Decide
        </Link>
        {" · "}
        {data.kind_label} · {data.project.title}
      </p>
      <h1 className="kos-title">{data.title}</h1>
      <p className="mt-2 text-sm text-(--color-text-muted)">
        {data.proposed_by.label}
        {data.proposed_display && <> · {data.proposed_display}</>}
      </p>
      <p className="mt-1 text-xs text-(--color-text-faint)">
        {data.labels.rule} {data.rule}
      </p>
      <div className="kos-card mt-6 px-5 py-4">
        <p className="mb-3 text-sm text-(--color-text)">
          {data.effect}
          {data.record.exists && (
            <>
              {" "}
              <Link
                to={`/r/${data.record.id}`}
                className="font-medium text-(--color-accent-text) underline decoration-1 underline-offset-[3px]"
              >
                {data.record.title}
              </Link>
            </>
          )}
        </p>
        <ChangeActions change={data} labels={data.labels} noticeLabels={data.notice_labels} pending={shownPending} />
      </div>
      {data.body_html !== null ? (
        <section className="mt-8">
          <Markdown html={data.body_html} />
        </section>
      ) : (
        <Diff data={data} />
      )}
    </div>
  );
}
