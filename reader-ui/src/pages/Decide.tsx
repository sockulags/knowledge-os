import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { ArrowRight, Bot, CircleHelp, Eye, FolderKanban, Inbox, MessagesSquare, User, Users } from "lucide-react";
import { api, ApiUnreachableError } from "../api/client";
import type { DecidePayload, ProposedDecision } from "../api/types";
import { PageSkeleton } from "../components/Skeleton";
import { LoadError } from "../components/Callout";
import { DecisionActions } from "../components/DecisionActions";
import { DecisionGuideToggle } from "../components/DecisionGuide";
import { EmptyState } from "../components/EmptyState";
import { useShell } from "../components/Shell";
import { networkErrorMessage } from "../lib/language";
import { useDocumentTitle } from "../hooks/useDocumentTitle";
import { showsOutcome } from "../lib/pendingActions";
import { useOnPendingSettled, usePendingEntries } from "../lib/pendingStore";

/** One small icon per kind of proposer (`proposed_by.source`); an unknown
 * source gets the neutral question mark, so a new kind needs no change here. */
const SOURCE_ICONS: Record<string, typeof User> = {
  you: User,
  conversation: MessagesSquare,
  meeting: Users,
  agent: Bot,
  observation: Eye,
};

function ProposalRow({ row, language }: { row: ProposedDecision; language: DecidePayload["language"] }) {
  const SourceIcon = SOURCE_ICONS[row.proposed_by.source] ?? CircleHelp;
  return (
    <li className="kos-card px-5 py-4">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-(--color-text-faint)">
        <span className="flex items-center gap-1">
          <FolderKanban size={12} />
          {row.project.title}
        </span>
        <span className="flex items-center gap-1" title={row.proposed_exact ?? undefined}>
          <SourceIcon size={12} />
          {row.proposed_by.label}
          {row.proposed_display && <> · {row.proposed_display}</>}
        </span>
      </div>
      <Link
        to={`/r/${row.id}`}
        className="mt-1.5 block rounded-sm font-serif text-[18px] font-semibold leading-snug hover:underline hover:decoration-1 hover:underline-offset-[3px]"
      >
        {row.title}
      </Link>
      {row.excerpt && <p className="mt-1 line-clamp-2 text-sm text-(--color-text-muted)">{row.excerpt}</p>}
      <p className="mt-2.5 flex items-start gap-1.5 text-sm text-(--color-text)">
        <ArrowRight size={14} className="mt-[3px] shrink-0 text-(--color-accent-text)" />
        <span>
          {row.effect}
          {row.replaces && (
            <>
              {" "}
              <Link
                to={`/r/${row.id}/compare`}
                className="font-medium text-(--color-accent-text) underline decoration-1 underline-offset-[3px]"
              >
                {language.labels.compare_short}
              </Link>
            </>
          )}
        </span>
      </p>
      <div className="mt-4 border-t border-(--color-border) pt-3.5">
        <DecisionActions
          variant="inline"
          target={{
            id: row.id,
            title: row.title,
            content_sha256: row.content_sha256,
            actions: row.actions,
            project_id: row.project.id,
            folder: "",
          }}
          language={language}
        />
      </div>
    </li>
  );
}

/** The decision inbox: every proposed decision, newest first, filterable by
 * project. Acting on a row removes it at once (one click, no dialog); the
 * notice offers Undo, which brings the row back. The list reloads in the
 * background once the write is saved. */
export function Decide() {
  const { nav } = useShell();
  useDocumentTitle(nav?.workspace_name, "Decide");
  const [params, setParams] = useSearchParams();
  const project = params.get("project");
  const [data, setData] = useState<DecidePayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const latest = useRef(0);
  // When the list request that `data` answers started.
  const [loadedAt, setLoadedAt] = useState(0);
  const entries = usePendingEntries();

  const load = useCallback(() => {
    const request = ++latest.current;
    const started = Date.now();
    api
      .proposedDecisions(project)
      .then((payload) => {
        if (request === latest.current) {
          setData(payload);
          setLoadedAt(started);
          setError(null);
        }
      })
      .catch((err: unknown) => {
        if (request !== latest.current) return;
        if (err instanceof ApiUnreachableError) setError(networkErrorMessage(nav?.language));
        else setError(err instanceof Error ? err.message : "Could not load the inbox.");
      });
  }, [project, nav]);

  useEffect(() => {
    load();
  }, [load]);

  useOnPendingSettled(load);

  if (error && !data) return <LoadError>{error}</LoadError>;
  if (!data) return <PageSkeleton />;

  // Rows accepted or withdrawn here leave the list from the click on.
  const acted = new Set(
    entries.filter((entry) => showsOutcome(entry, loadedAt)).map((entry) => entry.meta.recordId),
  );
  const items = data.items.filter((item) => !acted.has(item.id));
  const count = Math.max(data.count - acted.size, 0);
  const countLabel =
    count === 0
      ? null
      : count === 1
        ? data.count_templates.one
        : data.count_templates.other.replace("{count}", String(count));

  return (
    <div className="mx-auto w-full max-w-[760px] px-6 py-12 sm:px-10">
      <h1 className="kos-title">{data.title}</h1>
      <p className="kos-lede">{data.intro}</p>
      {countLabel && <p className="mt-1.5 text-sm text-(--color-text-faint)">{countLabel}</p>}

      <div className="mt-5">
        <DecisionGuideToggle language={data.language} defaultOpen={data.count === 0} />
      </div>

      {data.projects.length > 1 && (
        <nav className="mt-6 flex flex-wrap items-center gap-2" aria-label={data.filter_label}>
          <button type="button" className="kos-chip" aria-pressed={project === null} onClick={() => setParams({})}>
            {data.all_projects_label} · {count}
          </button>
          {data.projects.map((entry) => (
            <button
              key={entry.id}
              type="button"
              className="kos-chip"
              aria-pressed={project === entry.id}
              onClick={() => setParams({ project: entry.id })}
            >
              {entry.title} · {entry.count}
            </button>
          ))}
        </nav>
      )}

      {items.length === 0 ? (
        <div className="mt-8">
          <EmptyState title={data.empty.title} body={data.empty.body} icon={<Inbox size={28} strokeWidth={1.5} />} action={<></>} />
        </div>
      ) : (
        <ul className="mt-6 space-y-3">
          {items.map((row) => (
            <ProposalRow key={row.id} row={row} language={data.language} />
          ))}
        </ul>
      )}
    </div>
  );
}
