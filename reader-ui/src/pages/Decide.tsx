import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { ArrowRight, Bot, CircleHelp, Eye, FolderKanban, Inbox, MessagesSquare, User, Users } from "lucide-react";
import { api } from "../api/client";
import type { DecidePayload, ProposedDecision } from "../api/types";
import { PageSkeleton } from "../components/Skeleton";
import { Callout } from "../components/Callout";
import { DecisionActions } from "../components/DecisionActions";
import { DecisionGuideToggle } from "../components/DecisionGuide";
import { EmptyState } from "../components/EmptyState";
import { useShell } from "../components/Shell";

/** One small icon per kind of proposer (`proposed_by.source`); an unknown
 * source gets the neutral question mark, so a new kind needs no change here. */
const SOURCE_ICONS: Record<string, typeof User> = {
  you: User,
  conversation: MessagesSquare,
  meeting: Users,
  agent: Bot,
  observation: Eye,
};

function ProposalRow({
  row,
  language,
  onDone,
}: {
  row: ProposedDecision;
  language: DecidePayload["language"];
  onDone: (id: string) => void;
}) {
  const SourceIcon = SOURCE_ICONS[row.proposed_by.source] ?? CircleHelp;
  return (
    <li className="rounded-lg border border-(--color-border) bg-(--color-bg-raised) px-4 py-3.5">
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
      <Link to={`/r/${row.id}`} className="mt-1 block font-medium hover:underline hover:underline-offset-2">
        {row.title}
      </Link>
      {row.excerpt && <p className="mt-1 line-clamp-2 text-sm text-(--color-text-muted)">{row.excerpt}</p>}
      <p className="mt-2 flex items-start gap-1.5 text-sm text-(--color-text)">
        <ArrowRight size={14} className="mt-0.5 shrink-0 text-(--color-text-faint)" />
        <span>
          {row.effect}
          {row.replaces && (
            <>
              {" "}
              <Link to={`/r/${row.id}/compare`} className="text-(--color-text-muted) underline underline-offset-2">
                {language.labels.compare_short}
              </Link>
            </>
          )}
        </span>
      </p>
      <div className="mt-3">
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
          onDone={() => onDone(row.id)}
        />
      </div>
    </li>
  );
}

/** The decision inbox: every proposed decision, newest first, filterable by
 * project. Acting on a row removes it at once and reloads the list and the
 * sidebar count in the background, without a page reload. */
export function Decide() {
  const { refreshNav } = useShell();
  const [params, setParams] = useSearchParams();
  const project = params.get("project");
  const [data, setData] = useState<DecidePayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const latest = useRef(0);

  const load = useCallback(() => {
    const request = ++latest.current;
    api
      .proposedDecisions(project)
      .then((payload) => {
        if (request === latest.current) {
          setData(payload);
          setError(null);
        }
      })
      .catch((err: unknown) => {
        if (request === latest.current) setError(err instanceof Error ? err.message : "Could not load the inbox.");
      });
  }, [project]);

  useEffect(() => {
    load();
  }, [load]);

  function handleDone(id: string) {
    setData((current) =>
      current === null
        ? current
        : {
            ...current,
            items: current.items.filter((item) => item.id !== id),
            count: Math.max(current.count - 1, 0),
          },
    );
    refreshNav();
    load();
  }

  if (error && !data) return <Callout tone="danger">{error}</Callout>;
  if (!data) return <PageSkeleton />;

  const chipClass = (active: boolean) =>
    `rounded-full border px-2.5 py-1 text-xs ${
      active
        ? "border-(--color-border-strong) bg-(--color-bg-hover) font-medium text-(--color-text)"
        : "border-(--color-border) text-(--color-text-muted) hover:border-(--color-border-strong)"
    }`;

  return (
    <div className="mx-auto w-full max-w-[760px] px-6 py-12 sm:px-10">
      <h1 className="text-[28px] sm:text-[36px] font-semibold leading-tight tracking-tight">{data.title}</h1>
      <p className="mt-1.5 text-(--color-text-muted)">{data.intro}</p>
      {data.count_label && <p className="mt-1 text-sm text-(--color-text-faint)">{data.count_label}</p>}

      <div className="mt-5">
        <DecisionGuideToggle language={data.language} defaultOpen={data.count === 0} />
      </div>

      {data.projects.length > 1 && (
        <nav className="mt-6 flex flex-wrap items-center gap-2" aria-label={data.filter_label}>
          <button type="button" className={chipClass(project === null)} onClick={() => setParams({})}>
            {data.all_projects_label} · {data.count}
          </button>
          {data.projects.map((entry) => (
            <button
              key={entry.id}
              type="button"
              className={chipClass(project === entry.id)}
              onClick={() => setParams({ project: entry.id })}
            >
              {entry.title} · {entry.count}
            </button>
          ))}
        </nav>
      )}

      {data.items.length === 0 ? (
        <div className="mt-8">
          <EmptyState title={data.empty.title} body={data.empty.body} icon={<Inbox size={28} strokeWidth={1.5} />} action={<></>} />
        </div>
      ) : (
        <ul className="mt-6 space-y-3">
          {data.items.map((row) => (
            <ProposalRow key={row.id} row={row} language={data.language} onDone={handleDone} />
          ))}
        </ul>
      )}
    </div>
  );
}
