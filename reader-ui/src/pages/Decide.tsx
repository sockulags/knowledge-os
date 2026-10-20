import { useState } from "react";
import { Link, useSearchParams } from "react-router";
import {
  ArrowRight,
  Bot,
  CircleHelp,
  Eye,
  FilePen,
  FilePlus,
  FolderKanban,
  Inbox,
  MessagesSquare,
  User,
  Users,
} from "lucide-react";
import { api } from "../api/client";
import type { ChangesPayload, DecidePayload, ProposedChange, ProposedDecision } from "../api/types";
import { ChangeActions, changeKey } from "../components/ChangeActions";
import { PageSkeleton } from "../components/Skeleton";
import { Callout, LoadError } from "../components/Callout";
import { DecisionActions } from "../components/DecisionActions";
import { DecisionGuideToggle } from "../components/DecisionGuide";
import { EmptyState } from "../components/EmptyState";
import { changeLifecycle, decisionLifecycle, LifecycleStrip } from "../components/LifecycleStrip";
import { PendingObservations } from "../components/PendingObservations";
import { ReviewRules } from "../components/ReviewRules";
import { useShell } from "../components/Shell";
import { loadErrorMessage } from "../lib/language";
import { useApi } from "../hooks/useApi";
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
  // Every row in the inbox is a proposal: the strip shows where that sits.
  const lifecycle = decisionLifecycle(language, "draft");
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
      {lifecycle && <LifecycleStrip lifecycle={lifecycle} className="mt-2.5" />}
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

function ChangeRow({ row, payload }: { row: ProposedChange; payload: ChangesPayload }) {
  const SourceIcon = SOURCE_ICONS[row.proposed_by.source] ?? CircleHelp;
  const KindIcon = row.action === "create" ? FilePlus : FilePen;
  return (
    <li className="kos-card px-5 py-4" data-testid="change-row">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-(--color-text-faint)">
        <span className="flex items-center gap-1 font-medium text-(--color-text-muted)">
          <KindIcon size={12} />
          {row.kind_label}
        </span>
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
        to={`/c/${row.id}`}
        className="mt-1.5 block rounded-sm font-serif text-[18px] font-semibold leading-snug hover:underline hover:decoration-1 hover:underline-offset-[3px]"
      >
        {row.title}
      </Link>
      {row.excerpt && <p className="mt-1 line-clamp-2 text-sm text-(--color-text-muted)">{row.excerpt}</p>}
      <p className="mt-2.5 flex items-start gap-1.5 text-sm text-(--color-text)">
        <ArrowRight size={14} className="mt-[3px] shrink-0 text-(--color-accent-text)" />
        <span>
          {row.effect}{" "}
          <Link
            to={`/c/${row.id}`}
            className="font-medium text-(--color-accent-text) underline decoration-1 underline-offset-[3px]"
          >
            {payload.labels.show}
          </Link>
        </span>
      </p>
      <LifecycleStrip
        lifecycle={changeLifecycle()}
        className="mt-2"
        note={
          <>
            {payload.labels.rule} {row.rule}
          </>
        }
      />
      <div className="mt-4 border-t border-(--color-border) pt-3.5">
        <ChangeActions change={row} labels={payload.labels} noticeLabels={payload.notice_labels} />
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
  const entries = usePendingEntries();
  const [observationsWaiting, setObservationsWaiting] = useState(0);
  // The list stays on screen while it reloads after an action.
  const inbox = useApi(
    async () => {
      // When this list request started: `showsOutcome` compares it with
      // the time each pending action was taken.
      const loadedAt = Date.now();
      const [payload, changes] = await Promise.all([api.proposedDecisions(project), api.changes()]);
      return { payload, changes, loadedAt };
    },
    [project],
    { keepData: true },
  );

  useOnPendingSettled(inbox.reload);

  if (inbox.error && !inbox.data)
    return <LoadError>{loadErrorMessage(inbox, nav?.language, "Could not load the inbox.")}</LoadError>;
  if (!inbox.data) return <PageSkeleton />;
  const { payload: data, changes: changesData, loadedAt } = inbox.data;

  // Rows accepted or withdrawn here leave the list from the click on.
  const acted = new Set(
    entries.filter((entry) => showsOutcome(entry, loadedAt)).map((entry) => entry.meta.recordId),
  );
  const items = data.items.filter((item) => !acted.has(item.id));
  const changeRows = changesData.items.filter(
    (item) => !acted.has(changeKey(item.id)) && (project === null || item.project.id === project),
  );
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
        <DecisionGuideToggle language={data.language} defaultOpen={data.count === 0 && changesData.count === 0} />
      </div>

      <ReviewRules variant="full" />

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

      {changesData.policy_error && (
        <div className="mt-6">
          <Callout tone="danger">{changesData.policy_error}</Callout>
        </div>
      )}
      {changesData.broken.length > 0 && (
        <div className="mt-6">
          <Callout tone="danger">
            {changesData.broken.map((line) => (
              <p key={line}>{line}</p>
            ))}
          </Callout>
        </div>
      )}
      {changeRows.length > 0 && (
        <section className="mt-8" aria-label={changesData.heading}>
          <h2 className="kos-heading">{changesData.heading}</h2>
          <p className="mt-1 text-sm text-(--color-text-muted)">{changesData.intro}</p>
          <ul className="mt-4 space-y-3">
            {changeRows.map((row) => (
              <ChangeRow key={row.id} row={row} payload={changesData} />
            ))}
          </ul>
        </section>
      )}

      {items.length === 0 && changeRows.length > 0 ? null : items.length === 0 ? (
        <div className="mt-8">
          <EmptyState
            title={(observationsWaiting > 0 && data.empty.title_observations) || data.empty.title}
            body={data.empty.body}
            icon={<Inbox size={28} strokeWidth={1.5} />}
            action={<></>}
          />
        </div>
      ) : (
        <ul className="mt-6 space-y-3">
          {items.map((row) => (
            <ProposalRow key={row.id} row={row} language={data.language} />
          ))}
        </ul>
      )}

      <PendingObservations onCount={setObservationsWaiting} />
    </div>
  );
}
