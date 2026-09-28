// The documentation check of a project (issue #84): what changed in each
// linked repository since its last check, the page updates and decisions it
// suggests (each naming its commits), and recording the check once the pages
// are up to date. Nothing on this page writes until a button is pressed.

import { useState } from "react";
import { Link, useParams } from "react-router";
import { Bot, Check, ChevronRight, ExternalLink, PenLine, Scale } from "lucide-react";
import { api } from "../api/client";
import { code, isProposed } from "../api/write";
import type { CheckChange, CheckCommit, DecisionSuggestion, PageUpdateSuggestion, RepositoryCheck, WriteFailure } from "../api/types";
import { useApi } from "../hooks/useApi";
import { useShell } from "../components/Shell";
import { PageSkeleton } from "../components/Skeleton";
import { EmptyState } from "../components/EmptyState";
import { Callout, LoadError } from "../components/Callout";
import { WriteFailureCallout } from "../components/WriteFailureCallout";
import { loadErrorMessage } from "../lib/language";
import { useDocumentTitle } from "../hooks/useDocumentTitle";
import { agentBridge } from "../lib/agentBridge";
import { agentStore } from "../lib/agentStore";
import { documentationPrompt } from "../lib/agentPrompt";

const KIND_HEADINGS: Record<CheckChange["kind"], string> = {
  dependency: "Dependencies",
  command: "Commands",
  route: "API routes",
  configuration: "Configuration",
  module: "Modules",
  documentation: "Documentation",
};

/** A sentence from the check, with its `backticked` names shown as code. */
function Sentence({ text }: { text: string }) {
  return (
    <>
      {text.split(/(`[^`]+`)/).map((part, index) =>
        part.startsWith("`") && part.endsWith("`") && part.length > 1 ? (
          <code key={index} className="font-mono text-[0.85em]">
            {part.slice(1, -1)}
          </code>
        ) : (
          part
        ),
      )}
    </>
  );
}

function CommitChips({ shas, commits }: { shas: string[]; commits: CheckCommit[] }) {
  return (
    <span className="ml-1 inline-flex flex-wrap gap-1 align-middle">
      {shas.map((sha) => {
        const commit = commits.find((item) => item.sha === sha);
        return (
          <code
            key={sha}
            className="rounded bg-(--color-bg-sidebar) px-1 py-0.5 font-mono text-[11px] text-(--color-text-muted)"
            title={commit ? `${commit.subject} (${commit.author}, ${commit.date})` : sha}
          >
            {sha.slice(0, 7)}
          </code>
        );
      })}
    </span>
  );
}

function Fold({ title, children }: { title: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <section className="mt-6">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="kos-eyebrow mb-2 flex items-center gap-1.5 hover:text-(--color-text-muted)"
      >
        <ChevronRight size={13} className={open ? "rotate-90 transition-transform duration-100" : "transition-transform duration-100"} />
        {title}
      </button>
      {open && children}
    </section>
  );
}

function PageUpdate({
  suggestion,
  repo,
  onAgent,
}: {
  suggestion: PageUpdateSuggestion;
  repo: RepositoryCheck;
  onAgent: ((pages: PageUpdateSuggestion[]) => void) | null;
}) {
  return (
    <div className="kos-card px-3.5 py-3" data-testid="page-update">
      <div className="flex items-start justify-between gap-3">
        <Link to={`/r/${encodeURIComponent(suggestion.page)}`} className="text-sm font-medium hover:underline">
          {suggestion.title}
        </Link>
        <div className="flex shrink-0 gap-1">
          {onAgent && (
            <button type="button" onClick={() => onAgent([suggestion])} className="kos-btn kos-btn-ghost kos-btn-sm">
              <Bot size={14} />
              Update with the agent
            </button>
          )}
          <Link to={`/r/${encodeURIComponent(suggestion.page)}/edit`} className="kos-btn kos-btn-ghost kos-btn-sm">
            <PenLine size={14} />
            Edit
          </Link>
        </div>
      </div>
      <ul className="mt-1.5 space-y-1 text-sm text-(--color-text-muted)">
        {suggestion.reasons.map((reason) => (
          <li key={reason.text}>
            <Sentence text={reason.text} />
            <CommitChips shas={reason.commits} commits={repo.commits} />
          </li>
        ))}
      </ul>
    </div>
  );
}

function DecisionRow({ suggestion, repo, projectId }: { suggestion: DecisionSuggestion; repo: RepositoryCheck; projectId: string }) {
  const [done, setDone] = useState<{ id: string; held: boolean } | null>(null);
  const [failure, setFailure] = useState<WriteFailure | null>(null);
  const [busy, setBusy] = useState(false);
  const propose = async () => {
    setBusy(true);
    setFailure(null);
    const outcome = await code.propose(projectId, repo.path, suggestion.key);
    setBusy(false);
    if (!outcome.ok) setFailure(outcome.failure);
    else if (isProposed(outcome.data)) setDone({ id: outcome.data.proposal.record_id, held: true });
    else setDone({ id: outcome.data.id, held: false });
  };
  const existing = suggestion.existing ?? (done && !done.held ? done.id : null);
  return (
    <div className="kos-card px-3.5 py-3" data-testid="decision-suggestion">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-medium">{suggestion.title}</p>
          <p className="mt-0.5 text-sm text-(--color-text-muted)">
            <Sentence text={suggestion.summary} />
            <CommitChips shas={suggestion.commits} commits={repo.commits} />
          </p>
        </div>
        {existing ? (
          <Link to={`/r/${encodeURIComponent(existing)}`} className="kos-btn kos-btn-ghost kos-btn-sm shrink-0">
            <ExternalLink size={14} />
            {suggestion.existing ? "Already proposed" : "Proposed"}
          </Link>
        ) : done?.held ? (
          <span className="shrink-0 text-xs text-(--color-text-muted)">Waits in Decide</span>
        ) : (
          <button type="button" onClick={propose} disabled={busy} className="kos-btn kos-btn-secondary kos-btn-sm shrink-0">
            <Scale size={14} />
            Propose
          </button>
        )}
      </div>
      {failure && (
        <div className="mt-2">
          <WriteFailureCallout failure={failure} />
        </div>
      )}
    </div>
  );
}

function RepositoryReport({ repo, projectId, projectTitle, onMarked }: { repo: RepositoryCheck; projectId: string; projectTitle: string; onMarked: () => void }) {
  const [failure, setFailure] = useState<WriteFailure | null>(null);
  const [held, setHeld] = useState(false);
  const agentAvailable = agentBridge() !== null;
  const { nav } = useShell();

  const askAgent = agentAvailable
    ? (pages: PageUpdateSuggestion[]) => {
        const label =
          pages.length === 1
            ? `Update “${pages[0].title}” for the code changes the documentation check found.`
            : `Update ${pages.length} pages for the code changes the documentation check found.`;
        void agentStore.sendFromPage(
          "draft",
          documentationPrompt({ id: projectId, title: projectTitle }, repo, pages),
          { workspaceName: nav?.workspace_name ?? null, page: null, project: { id: projectId, title: projectTitle } },
          label,
        );
      }
    : null;

  const mark = async () => {
    if (repo.head === null) return;
    setFailure(null);
    const outcome = await code.mark(projectId, repo.path, repo.head);
    if (!outcome.ok) setFailure(outcome.failure);
    else if (isProposed(outcome.data)) setHeld(true);
    else onMarked();
  };

  const byKind = new Map<CheckChange["kind"], CheckChange[]>();
  for (const change of repo.changes) byKind.set(change.kind, [...(byKind.get(change.kind) ?? []), change]);

  return (
    <section className="mt-10" data-testid="repository-check">
      <h2 className="kos-heading">{repo.label}</h2>
      <p className="mt-1 text-sm text-(--color-text-muted)">
        {repo.message}
        {repo.base && repo.head && repo.state === "changed" && (
          <>
            {" "}
            <span className="font-mono text-xs">
              {repo.base.slice(0, 7)}..{repo.head.slice(0, 7)}
            </span>
          </>
        )}
      </p>
      {repo.state === "unavailable" && (
        <div className="mt-3">
          <Callout tone="danger">{repo.message}</Callout>
        </div>
      )}
      {repo.state === "changed" && (
        <>
          <section className="mt-6">
            <div className="mb-2.5 flex items-center justify-between gap-2">
              <h3 className="kos-eyebrow">Pages to update</h3>
              {askAgent && repo.pages.length > 1 && (
                <button type="button" onClick={() => askAgent(repo.pages)} className="kos-btn kos-btn-ghost kos-btn-sm">
                  <Bot size={14} />
                  Update all with the agent
                </button>
              )}
            </div>
            {repo.pages.length === 0 ? (
              <p className="text-sm text-(--color-text-faint)">No page mentions anything these commits changed.</p>
            ) : (
              <div className="space-y-1.5">
                {repo.pages.map((suggestion) => (
                  <PageUpdate key={suggestion.page} suggestion={suggestion} repo={repo} onAgent={askAgent} />
                ))}
              </div>
            )}
          </section>

          <section className="mt-6">
            <h3 className="kos-eyebrow mb-2.5">Decisions to propose</h3>
            {repo.decisions.length === 0 ? (
              <p className="text-sm text-(--color-text-faint)">Nothing here reads like a decision: no dependency or module was added or removed.</p>
            ) : (
              <div className="space-y-1.5">
                {repo.decisions.map((suggestion) => (
                  <DecisionRow key={suggestion.key} suggestion={suggestion} repo={repo} projectId={projectId} />
                ))}
              </div>
            )}
          </section>

          <Fold title={`What changed (${repo.changes.length})`}>
            <div className="space-y-3 text-sm">
              {[...byKind.entries()].map(([kind, changes]) => (
                <div key={kind}>
                  <p className="font-medium">{KIND_HEADINGS[kind]}</p>
                  <ul className="mt-1 space-y-0.5 text-(--color-text-muted)">
                    {changes.map((change) => (
                      <li key={change.key}>
                        <span className="capitalize">{change.action}</span> <code className="font-mono text-xs">{change.name}</code>
                        {change.detail && <span> ({change.detail})</span>}
                        <CommitChips shas={change.commits} commits={repo.commits} />
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </Fold>

          <Fold title={`Commits (${repo.commits.length}${repo.commits_truncated ? "+" : ""})`}>
            <ul className="space-y-1 text-sm">
              {repo.commits.map((commit) => (
                <li key={commit.sha} className="flex gap-2">
                  <code className="shrink-0 font-mono text-xs text-(--color-text-muted)">{commit.short}</code>
                  <span className="min-w-0">
                    {commit.subject} <span className="text-xs text-(--color-text-faint)">{commit.author}, {commit.date}</span>
                  </span>
                </li>
              ))}
            </ul>
          </Fold>

          <div className="mt-8 border-t border-(--color-border) pt-4">
            {failure && <WriteFailureCallout failure={failure} />}
            {held && <Callout>Recording the check waits for review in Decide.</Callout>}
            <div className="flex flex-wrap items-center gap-3">
              <button type="button" onClick={mark} className="kos-btn kos-btn-primary kos-btn-sm" data-testid="mark-checked">
                <Check size={14} />
                Mark as checked up to {repo.head?.slice(0, 7)}
              </button>
              <p className="text-xs text-(--color-text-muted)">When the pages are up to date. The next check starts at this commit.</p>
            </div>
          </div>
        </>
      )}
    </section>
  );
}

export function DocumentationCheck() {
  const { projectId } = useParams<{ projectId: string }>();
  const [version, setVersion] = useState(0);
  const state = useApi(() => api.documentationCheck(projectId!), [projectId, version]);
  const { nav } = useShell();
  const projectTitle = nav?.projects.find((project) => project.id === projectId)?.title ?? projectId ?? "";
  useDocumentTitle(nav?.workspace_name, `Documentation check · ${projectTitle}`);

  if (state.loading) return <PageSkeleton />;
  if (state.notFound)
    return <EmptyState title="Project not found" body={`No project named "${projectId}" exists in this workspace.`} />;
  if (state.error || !state.data)
    return <LoadError>{loadErrorMessage(state, nav?.language, "Could not check the documentation.")}</LoadError>;

  return (
    <div className="mx-auto w-full max-w-[760px] px-6 py-12 sm:px-10">
      <Link to={`/p/${encodeURIComponent(projectId!)}`} className="text-sm text-(--color-text-muted) hover:underline">
        {projectTitle}
      </Link>
      <h1 className="kos-title">Documentation check</h1>
      <p className="kos-lede mt-2">
        What changed in the code since the documentation was last checked, and what that suggests for this project's pages
        and decisions. Nothing is changed until you choose to.
      </p>
      {state.data.repositories.length === 0 ? (
        <div className="mt-8">
          <Callout>
            This project links no code repository yet. Link one in the Code section of the{" "}
            <Link to={`/p/${encodeURIComponent(projectId!)}`} className="underline">
              project page
            </Link>
            .
          </Callout>
        </div>
      ) : (
        state.data.repositories.map((repo) => (
          <RepositoryReport
            key={repo.path}
            repo={repo}
            projectId={projectId!}
            projectTitle={projectTitle}
            onMarked={() => setVersion((value) => value + 1)}
          />
        ))
      )}
    </div>
  );
}
