// The "Code" section of a project page (issue #84): the repositories the
// project links, each with the commit its documentation was last checked
// against, a way to link another, and the way to the documentation check.

import { useState } from "react";
import { Link } from "react-router";
import { FolderGit2, GitCommitHorizontal, Link2, ListChecks, Unlink } from "lucide-react";
import { api } from "../api/client";
import { code, isProposed } from "../api/write";
import type { RepositoryLink, WriteFailure } from "../api/types";
import { useApi } from "../hooks/useApi";
import { WriteFailureCallout } from "./WriteFailureCallout";
import { Callout } from "./Callout";

function RepositoryRow({ link, projectId, onChanged }: { link: RepositoryLink; projectId: string; onChanged: () => void }) {
  const [failure, setFailure] = useState<WriteFailure | null>(null);
  const unlink = async () => {
    if (!window.confirm(`Unlink ${link.label}? The repository itself is not touched.`)) return;
    const outcome = await code.unlink(projectId, link.path);
    if (outcome.ok) onChanged();
    else setFailure(outcome.failure);
  };
  return (
    <div className="kos-card px-3.5 py-2.5" data-testid="code-repository">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="flex items-center gap-1.5 truncate text-sm font-medium">
            <FolderGit2 size={14} className="shrink-0 text-(--color-text-faint)" />
            {link.label}
          </p>
          <p className="mt-0.5 truncate font-mono text-xs text-(--color-text-muted)" title={link.folder}>
            {link.path}
          </p>
          <p className="mt-1 flex items-center gap-1 text-xs text-(--color-text-muted)">
            <GitCommitHorizontal size={13} />
            {link.checked ? `Documentation checked against ${link.checked.slice(0, 7)} on ${link.checked_on}` : "Not checked yet"}
          </p>
          {!link.found && (
            <p className="mt-1 text-xs text-(--color-accent-red-text)">
              Not found on this computer{link.remote ? `; clone ${link.remote} to ${link.folder}` : ""}.
            </p>
          )}
        </div>
        <button type="button" onClick={unlink} className="kos-btn kos-btn-ghost kos-btn-sm shrink-0" aria-label={`Unlink ${link.label}`}>
          <Unlink size={14} />
        </button>
      </div>
      {failure && (
        <div className="mt-2">
          <WriteFailureCallout failure={failure} />
        </div>
      )}
    </div>
  );
}

function LinkForm({ projectId, onLinked, onCancel }: { projectId: string; onLinked: () => void; onCancel: () => void }) {
  const [path, setPath] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<WriteFailure | null>(null);
  const [held, setHeld] = useState(false);
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!path.trim()) return;
    setBusy(true);
    setFailure(null);
    const outcome = await code.link(projectId, path.trim());
    setBusy(false);
    if (!outcome.ok) setFailure(outcome.failure);
    else if (isProposed(outcome.data)) setHeld(true);
    else onLinked();
  };
  return (
    <form onSubmit={submit} className="kos-card mt-1.5 space-y-2 px-3.5 py-3" data-testid="link-repository-form">
      <label className="block text-sm font-medium" htmlFor="repository-path">
        Repository folder
      </label>
      <input
        id="repository-path"
        className="kos-input w-full font-mono text-sm"
        value={path}
        onChange={(event) => setPath(event.target.value)}
        placeholder="D:\code\my-project, or a path relative to the knowledge base"
        autoFocus
      />
      <p className="text-xs text-(--color-text-muted)">
        A Git repository on this computer. Checks start at its current commit, so the first check shows what changes after today.
      </p>
      {failure && <WriteFailureCallout failure={failure} />}
      {held && <Callout>The link waits for review in Decide, as the review rules ask.</Callout>}
      <div className="flex gap-2">
        <button type="submit" disabled={busy || !path.trim()} className="kos-btn kos-btn-primary kos-btn-sm">
          Link
        </button>
        <button type="button" onClick={onCancel} className="kos-btn kos-btn-ghost kos-btn-sm">
          Cancel
        </button>
      </div>
    </form>
  );
}

export function CodeRepositories({ projectId }: { projectId: string }) {
  const [version, setVersion] = useState(0);
  const [linking, setLinking] = useState(false);
  const state = useApi(() => api.repositories(projectId), [projectId, version]);
  const links = state.data?.repositories ?? [];
  const reload = () => setVersion((value) => value + 1);

  return (
    <section className="mt-10" data-testid="code-section">
      <div className="mb-2.5 flex items-center justify-between gap-2">
        <h3 className="kos-eyebrow">Code</h3>
        <div className="no-print flex items-center gap-1">
          {links.length > 0 && (
            <Link to={`/p/${encodeURIComponent(projectId)}/code`} className="kos-btn kos-btn-secondary kos-btn-sm">
              <ListChecks size={14} />
              Check documentation
            </Link>
          )}
          {!linking && (
            <button type="button" onClick={() => setLinking(true)} className="kos-btn kos-btn-ghost kos-btn-sm">
              <Link2 size={14} />
              Link a repository
            </button>
          )}
        </div>
      </div>
      {links.length === 0 && !linking && (
        <p className="text-sm text-(--color-text-faint)">
          Link the code this project describes, and the documentation check lists which pages its commits make out of date.
        </p>
      )}
      <div className="space-y-1.5">
        {links.map((link) => (
          <RepositoryRow key={link.path} link={link} projectId={projectId} onChanged={reload} />
        ))}
      </div>
      {linking && (
        <LinkForm
          projectId={projectId}
          onLinked={() => {
            setLinking(false);
            reload();
          }}
          onCancel={() => setLinking(false)}
        />
      )}
    </section>
  );
}
