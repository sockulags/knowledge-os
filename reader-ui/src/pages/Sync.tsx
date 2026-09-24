import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Check, GitMerge } from "lucide-react";
import { api } from "../api/client";
import type { ConflictFile, SyncFailure, SyncStatus } from "../api/types";
import { sync as syncApi } from "../api/write";
import { Callout } from "../components/Callout";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { useShell } from "../components/Shell";
import { relativeTime } from "../hooks/useSync";
import { useDocumentTitle } from "../hooks/useDocumentTitle";

type Issue = { path: string; message: string };

function plural(count: number, noun: string): string {
  return `${count} ${count === 1 ? noun : `${noun}s`}`;
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex gap-4 py-2 text-sm">
      <dt className="w-40 shrink-0 text-(--color-text-faint)">{label}</dt>
      <dd className="min-w-0 break-words">{children}</dd>
    </div>
  );
}

function IssueList({ issues }: { issues: Issue[] }) {
  return (
    <ul className="mt-2 space-y-1">
      {issues.map((issue, index) => (
        <li key={index}>
          <span className="break-all font-mono text-xs opacity-90">{issue.path}</span>
          <span className="block">{issue.message}</span>
        </li>
      ))}
    </ul>
  );
}

function StatusDetails({ status }: { status: SyncStatus }) {
  if (!status.available) {
    return (
      <Callout>
        <p className="font-medium">Changes are not versioned or synced.</p>
        <p className="mt-1 whitespace-pre-wrap">{status.detail}</p>
      </Callout>
    );
  }
  const branch = status.branch ?? "main";
  return (
    <>
      <dl className="kos-card mb-6 divide-y divide-(--color-border) px-4 py-0.5">
        <Row label="Branch">{status.branch ?? "Not on a branch"}</Row>
        <Row label="Syncs with">{status.upstream ?? "Nothing yet"}</Row>
        <Row label="To push">
          {status.ahead} {status.ahead === 1 ? "commit" : "commits"}
        </Row>
        <Row label="To pull">
          {status.behind} {status.behind === 1 ? "commit" : "commits"} (as of the last sync)
        </Row>
        <Row label="Not committed">
          {status.merging
            ? "Held until this sync finishes"
            : status.uncommitted === 0
            ? "Nothing"
            : `${status.uncommitted} changed ${status.uncommitted === 1 ? "file" : "files"}, made outside the app`}
        </Row>
        <Row label="Last sync">{status.last_sync ? relativeTime(status.last_sync) : "Never from this computer"}</Row>
        <Row label="Commits as">
          {status.identity ? `${status.identity.name} <${status.identity.email}>` : "No Git identity set"}
        </Row>
      </dl>
      {status.identity === null && (
        <Callout tone="danger">
          <p className="font-medium">Git does not know who you are, so nothing is committed.</p>
          <p className="mt-1">
            Run <code>git config user.name "Your Name"</code> and <code>git config user.email you@example.com</code> in
            this knowledge base's folder (add <code>--global</code> to use them everywhere).
          </p>
        </Callout>
      )}
      {status.upstream === null && (
        <Callout>
          <p className="font-medium">There is nowhere to sync to yet.</p>
          {status.remotes.length === 0 ? (
            <p className="mt-1">
              Add a remote and publish this branch: <code>git remote add origin &lt;url&gt;</code>, then{" "}
              <code>git push -u origin {branch}</code>.
            </p>
          ) : (
            <p className="mt-1">
              Publish this branch to set its upstream: <code>git push -u {status.remotes[0]} {branch}</code>.
            </p>
          )}
        </Callout>
      )}
      {status.warnings.map((warning) => (
        <Callout key={warning}>{warning}</Callout>
      ))}
    </>
  );
}

function Version({ label, text, onChoose, busy }: { label: string; text: string | null; onChoose: () => void; busy: boolean }) {
  return (
    <div className="flex min-w-0 flex-col overflow-hidden rounded-(--radius-card) border border-(--color-border) bg-(--color-bg-raised)">
      <div className="flex items-center justify-between gap-2 border-b border-(--color-border) bg-(--color-bg-sidebar) px-3 py-2">
        <span className="kos-eyebrow text-(--color-text-muted)">{label}</span>
        <button type="button" onClick={onChoose} disabled={busy} className="kos-btn kos-btn-secondary kos-btn-sm text-xs">
          {text === null ? "Delete the file" : "Keep this version"}
        </button>
      </div>
      <pre className="max-h-96 min-h-24 flex-1 overflow-auto whitespace-pre-wrap break-words px-3 py-2 font-mono text-xs leading-relaxed">
        {text ?? "(deleted on this side)"}
      </pre>
    </div>
  );
}

function ConflictCard({
  file,
  upstream,
  issues,
  onResolved,
}: {
  file: ConflictFile;
  upstream: string | null;
  issues: Issue[];
  onResolved: (path: string, issues: Issue[]) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(file.working ?? file.ours ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reopened, setReopened] = useState(false);

  async function choose(choice: "ours" | "theirs" | "merged", content?: string) {
    setBusy(true);
    setError(null);
    const outcome = await syncApi.resolve(file.path, choice, content);
    setBusy(false);
    if (outcome.ok) {
      setEditing(false);
      setReopened(false);
      onResolved(file.path, outcome.data.issues);
    } else {
      setError(outcome.failure.detail);
    }
  }

  const open = !file.resolved || reopened;

  return (
    <section className="kos-card mb-6 p-5" data-conflict={file.path}>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h3 className="break-all font-mono text-sm font-medium">{file.path}</h3>
        {file.resolved && !reopened ? (
          <span className="inline-flex items-center gap-1 rounded-[5px] bg-(--color-accent-green-bg) px-1.5 py-[3px] text-xs font-medium leading-none text-(--color-accent-green-text)">
            <Check size={12} /> Version chosen
          </span>
        ) : (
          <span className="inline-flex items-center gap-1.5 rounded-[5px] bg-(--color-accent-amber-bg) px-1.5 py-[3px] text-xs font-medium leading-none text-(--color-accent-amber-text)">
            <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden="true" />
            Changed on both sides
          </span>
        )}
      </div>

      {issues.length > 0 && (
        <Callout tone="danger">
          <p className="font-medium">This version does not pass lint, so the sync cannot finish with it.</p>
          <IssueList issues={issues} />
        </Callout>
      )}
      {error && (
        <Callout tone="danger">
          <p>{error}</p>
        </Callout>
      )}

      {!open ? (
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => setReopened(true)}
            className="kos-btn kos-btn-ghost"
          >
            Choose again
          </button>
        </div>
      ) : file.binary ? (
        <p className="text-sm text-(--color-text-muted)">
          This file is not text, so it cannot be shown or edited here. Resolve it with Git, or cancel the sync.
        </p>
      ) : (
        <>
          <div className="grid gap-3 md:grid-cols-2">
            <Version label="This computer" text={file.ours} busy={busy} onChoose={() => choose("ours")} />
            <Version
              label={`Incoming${upstream ? ` from ${upstream}` : ""}`}
              text={file.theirs}
              busy={busy}
              onChoose={() => choose("theirs")}
            />
          </div>
          {editing ? (
            <div className="mt-3">
              <label className="mb-1.5 block text-[13px] font-medium text-(--color-text-muted)">
                Merged text
              </label>
              <textarea
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                spellCheck={false}
                className="kos-input h-80 rounded-(--radius-card) p-3 font-mono text-xs leading-relaxed"
              />
              <div className="mt-2 flex gap-2">
                <button
                  type="button"
                  disabled={busy || /^(<<<<<<<|>>>>>>>)( |$)/m.test(draft)}
                  onClick={() => choose("merged", draft)}
                  className="kos-btn kos-btn-primary"
                >
                  Use this text
                </button>
                <button
                  type="button"
                  onClick={() => setEditing(false)}
                  className="kos-btn kos-btn-ghost"
                >
                  Cancel
                </button>
                {/^(<<<<<<<|>>>>>>>)( |$)/m.test(draft) && (
                  <span className="self-center text-xs text-(--color-text-muted)">
                    Remove the conflict markers first.
                  </span>
                )}
              </div>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setEditing(true)}
              className="kos-btn kos-btn-ghost mt-3"
            >
              Edit a merged version
            </button>
          )}
        </>
      )}
    </section>
  );
}

/** The sync page: the repository's state and, while a pull is waiting on
 * conflicts, each conflicting file with both versions side by side. */
export function Sync() {
  const { sync, nav } = useShell();
  const [files, setFiles] = useState<ConflictFile[] | null>(null);
  const [issuesByPath, setIssuesByPath] = useState<Record<string, Issue[]>>({});
  const [finishFailure, setFinishFailure] = useState<SyncFailure | null>(null);
  const [confirmAbort, setConfirmAbort] = useState(false);
  const [aborting, setAborting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const status = sync.status;
  const merging = status?.merging ?? false;
  useDocumentTitle(nav?.workspace_name, "Sync");

  const loadConflicts = useCallback(() => {
    api
      .syncConflicts()
      .then((payload) => setFiles(payload.files))
      .catch(() => setFiles([]));
  }, []);

  useEffect(() => {
    if (merging) loadConflicts();
    else setFiles(null);
  }, [merging, loadConflicts]);

  const unresolved = files?.filter((file) => !file.resolved).length ?? 0;

  async function finish() {
    setFinishFailure(null);
    setMessage(null);
    const outcome = await sync.run();
    if (outcome.ok) {
      setIssuesByPath({});
    } else {
      setFinishFailure(outcome.failure as SyncFailure);
      loadConflicts();
    }
  }

  async function abort() {
    setAborting(true);
    const outcome = await syncApi.abort();
    setAborting(false);
    setConfirmAbort(false);
    sync.refresh();
    if (outcome.ok) setMessage("The sync was cancelled. Your files are back to how they were before it.");
  }

  return (
    <div className="mx-auto w-full max-w-[1000px] px-6 py-12 sm:px-10">
      <h1 className="kos-title mb-8">Sync</h1>

      {sync.lastResult && !merging && (
        <Callout icon={<Check size={16} />}>
          <p>
            Synced. {plural(sync.lastResult.pulled, "commit")} pulled, {plural(sync.lastResult.pushed, "commit")} pushed.
            {sync.lastResult.index_error && ` The search index could not be rebuilt: ${sync.lastResult.index_error}`}
          </p>
        </Callout>
      )}
      {message && (
        <Callout icon={<Check size={16} />}>
          <p>{message}</p>
        </Callout>
      )}
      {status === null ? <p className="text-sm text-(--color-text-muted)">Reading the repository…</p> : <StatusDetails status={status} />}

      {sync.failure && !merging && sync.failure.error !== "conflict" && (
        <Callout tone="danger">
          <p className="font-medium">The last sync did not finish.</p>
          <p className="mt-1 whitespace-pre-wrap break-words">{sync.failure.detail}</p>
          {sync.failure.issues && <IssueList issues={sync.failure.issues} />}
        </Callout>
      )}

      {merging && (
        <>
          <h2 className="kos-heading mb-2 mt-10 flex items-center gap-2">
            <GitMerge size={19} className="text-(--color-accent-text)" /> Resolve conflicts
          </h2>
          <p className="mb-6 max-w-[70ch] text-sm leading-relaxed text-(--color-text-muted)">
            These files changed both on this computer and on {status?.upstream ?? "the remote"} since the last sync.
            Nothing has been overwritten. Choose a version for each file or write a merged one, then finish the sync.
          </p>

          {files?.map((file) => (
            <ConflictCard
              key={`${file.path}:${file.resolved}`}
              file={file}
              upstream={status?.upstream ?? null}
              issues={issuesByPath[file.path] ?? []}
              onResolved={(path, issues) => {
                setIssuesByPath((current) => ({ ...current, [path]: issues }));
                setFinishFailure(null);
                sync.refresh();
                loadConflicts();
              }}
            />
          ))}

          {finishFailure && (
            <Callout tone="danger">
              <p className="font-medium">
                {finishFailure.error === "lint" ? "The result does not pass lint yet." : "The sync did not finish."}
              </p>
              <p className="mt-1 whitespace-pre-wrap break-words">{finishFailure.detail}</p>
              {finishFailure.issues && <IssueList issues={finishFailure.issues} />}
            </Callout>
          )}

          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              disabled={unresolved > 0 || sync.busy}
              onClick={finish}
              className="kos-btn kos-btn-primary px-4 py-2"
            >
              {sync.busy ? "Finishing…" : "Finish sync"}
            </button>
            <button
              type="button"
              onClick={() => setConfirmAbort(true)}
              className="kos-btn kos-btn-ghost py-2"
            >
              Cancel sync
            </button>
            {unresolved > 0 && (
              <span className="text-sm text-(--color-text-muted)">
                {unresolved} {unresolved === 1 ? "file needs" : "files need"} a version first.
              </span>
            )}
          </div>
        </>
      )}

      {confirmAbort && (
        <ConfirmDialog
          title="Cancel this sync?"
          confirmLabel="Cancel sync"
          busy={aborting}
          onConfirm={abort}
          onCancel={() => setConfirmAbort(false)}
        >
          Every file returns to how it was before this sync, including choices made here. Your own commits stay, and
          the incoming changes come back the next time you sync.
        </ConfirmDialog>
      )}
    </div>
  );
}
