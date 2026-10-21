import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { api } from "../api/client";
import type { EditableMetadata, RecordPayload, WriteFailure, WriteResult } from "../api/types";
import { interfaceReference, isProposed, write } from "../api/write";
import { useApi } from "../hooks/useApi";
import { useUnsavedChanges } from "../hooks/useUnsavedChanges";
import { useShell } from "../components/Shell";
import { PageSkeleton } from "../components/Skeleton";
import { Breadcrumb } from "../components/Breadcrumb";
import { RecordNotFound } from "../components/EmptyState";
import { Callout, LoadError } from "../components/Callout";
import { loadErrorMessage } from "../lib/language";
import { useDocumentTitle } from "../hooks/useDocumentTitle";
import { MarkdownEditor } from "../components/MarkdownEditor";
import { ConflictCallout, WriteFailureCallout } from "../components/WriteFailureCallout";
import { ConflictComparison } from "../components/ConflictComparison";
import { PagePicker, linkablePages } from "../components/PagePicker";
import {
  Field,
  PrimaryButton,
  SecondaryButton,
  UnsavedChangesDialog,
  inputClass,
  parseList,
} from "../components/EditorParts";

interface Draft {
  title: string;
  description: string;
  tags: string;
  related: string[];
  sources: string[];
  body: string;
}

function draftFrom(metadata: EditableMetadata, body: string): Draft {
  return {
    title: metadata.title,
    description: metadata.description,
    tags: metadata.tags.join(", "),
    related: metadata.related,
    sources: metadata.sources,
    body,
  };
}

/** The fields that differ from the saved revision, as PATCH metadata (an
 * emptied list or description is removed rather than written empty). */
function metadataChanges(saved: Draft, draft: Draft): Record<string, unknown> {
  const changes: Record<string, unknown> = {};
  if (draft.title.trim() !== saved.title) changes.title = draft.title.trim();
  const description = draft.description.trim();
  if (description !== saved.description) changes.description = description || null;
  const lists = {
    tags: [parseList(draft.tags), parseList(saved.tags)],
    related: [draft.related, saved.related],
    sources: [draft.sources, saved.sources],
  };
  for (const [field, [next, before]] of Object.entries(lists)) {
    if (next.join(",") !== before.join(",")) changes[field] = next.length > 0 ? next : null;
  }
  return changes;
}

const FIELD_LABELS: Record<string, string> = {
  title: "title",
  description: "description",
  tags: "tags",
  related: "related pages",
  sources: "based on",
};

/** The revision a save is made against: its fields as loaded, and its hash. */
interface Base {
  saved: Draft;
  sha: string;
}

type Status =
  | { kind: "idle" }
  | { kind: "saving" }
  | { kind: "saved"; at: Date; indexError: string | null }
  // `current` is the version now on disk: "loading" while it is fetched,
  // null when it could not be (then only a reload is offered).
  | { kind: "conflict"; current: Base | "loading" | null }
  | { kind: "failed"; failure: WriteFailure };

export function EditRecord() {
  const { recordId } = useParams<{ recordId: string }>();
  const navigate = useNavigate();
  const { refreshNav, nav } = useShell();
  const [loadKey, setLoadKey] = useState(0);
  const apiState = useApi(() => api.record(recordId!), [recordId, loadKey]);
  const { data, loading, notFound } = apiState;
  useDocumentTitle(nav?.workspace_name, data ? `Edit ${data.title}` : null);

  if (loading) return <PageSkeleton />;
  if (notFound) return <RecordNotFound nav={nav} recordId={recordId} />;
  if (apiState.error || !data)
    return <LoadError>{loadErrorMessage(apiState, nav?.language, "Could not load this page.")}</LoadError>;
  if (!data.editing.editable || data.editing.metadata === null || data.editing.raw_body === null) {
    return (
      <div className="mx-auto w-full max-w-[720px] px-6 py-12 sm:px-10">
        <Callout>
          This kind of page cannot be edited here.{" "}
          <Link to={`/r/${data.id}`} className="font-medium text-(--color-accent-text) underline underline-offset-[3px]">
            Back to the page
          </Link>
        </Callout>
      </div>
    );
  }
  return (
    <Editor
      key={`${data.id}:${loadKey}`}
      record={data}
      onReload={() => setLoadKey((value) => value + 1)}
      onClose={() => navigate(`/r/${data.id}`)}
      refreshNav={refreshNav}
    />
  );
}

function Editor({
  record,
  onReload,
  onClose,
  refreshNav,
}: {
  record: RecordPayload;
  onReload: () => void;
  onClose: () => void;
  refreshNav: () => void;
}) {
  const editing = record.editing;
  const { nav } = useShell();
  const [saved, setSaved] = useState<Draft>(() => draftFrom(editing.metadata!, editing.raw_body!));
  const [draft, setDraft] = useState<Draft>(saved);
  const [sha, setSha] = useState(editing.content_sha256!);
  const [status, setStatus] = useState<Status>({ kind: "idle" });
  const [nonMaterial, setNonMaterial] = useState(false);
  // An attachment still being stored leaves a placeholder link in the text.
  const [uploading, setUploading] = useState(false);

  const changes = metadataChanges(saved, draft);
  const bodyChanged = draft.body !== saved.body;
  const dirty = bodyChanged || Object.keys(changes).length > 0;
  const needsConfirmation = editing.body_change_needs_confirmation && bodyChanged;
  const { blocker, allowNextNavigation } = useUnsavedChanges(dirty);
  const navigate = useNavigate();
  const canSave = dirty && status.kind !== "saving" && !uploading && !(needsConfirmation && !nonMaterial);

  /** On a conflict, fetch the version now on disk to compare against. */
  const loadCurrent = useCallback(async () => {
    setStatus({ kind: "conflict", current: "loading" });
    let current: Base | null = null;
    try {
      const fresh = (await api.record(record.id)).editing;
      if (fresh.editable && fresh.metadata && fresh.raw_body !== null && fresh.content_sha256) {
        current = { saved: draftFrom(fresh.metadata, fresh.raw_body), sha: fresh.content_sha256 };
      }
    } catch {
      current = null;
    }
    setStatus({ kind: "conflict", current });
  }, [record.id]);

  /** Send the draft's differences from `base`, against `base`'s hash.
   * Resolves true when the draft is on disk; false when it is not (a
   * conflict, a refused write, or an edit held back for review). */
  const submit = useCallback(async (base: Base): Promise<boolean> => {
    const changes = metadataChanges(base.saved, draft);
    const bodyChanged = draft.body !== base.saved.body;
    const needsConfirmation = editing.body_change_needs_confirmation && bodyChanged;
    if (!bodyChanged && Object.keys(changes).length === 0) {
      setStatus({ kind: "idle" });
      return true;
    }
    // What this save sends. The text stays editable meanwhile, so the draft
    // may move on; only `saved` takes this snapshot, and whatever was typed
    // since still reads as unsaved.
    const sent = { ...draft, title: draft.title.trim(), description: draft.description.trim() };
    setStatus({ kind: "saving" });
    const outcome = await write.edit(record.id, {
      expected_sha256: base.sha,
      ...(Object.keys(changes).length > 0 ? { metadata: changes } : {}),
      ...(bodyChanged ? { body: sent.body } : {}),
      ...(needsConfirmation ? { confirm_non_material: true, change_reference: interfaceReference("edit") } : {}),
    });
    if (outcome.ok && isProposed(outcome.data)) {
      // The review rules held the edit back: the page is unchanged, and the
      // proposed change waits in Decide.
      allowNextNavigation();
      refreshNav();
      navigate(`/c/${outcome.data.proposal.id}`);
      return false;
    } else if (outcome.ok) {
      const written = outcome.data as WriteResult;
      // The returned hash is the revision now on disk: the next save sends it.
      setSha(written.content_sha256);
      setSaved(sent);
      setNonMaterial(false);
      setStatus({ kind: "saved", at: new Date(), indexError: written.index.error });
      if ("title" in changes) refreshNav();
      return true;
    } else if (outcome.failure.error === "conflict") {
      void loadCurrent();
    } else {
      setStatus({ kind: "failed", failure: outcome.failure });
    }
    return false;
  }, [editing.body_change_needs_confirmation, record.id, draft, refreshNav, allowNextNavigation, navigate, loadCurrent]);

  const save = useCallback(async () => (canSave ? submit({ saved, sha }) : false), [canSave, submit, saved, sha]);

  /** Build on the version now on disk: from here on the draft is compared
   * with, and saved against, that version. */
  const adopt = (current: Base) => {
    setSaved(current.saved);
    setSha(current.sha);
    setNonMaterial(false);
  };
  const keepMine = (current: Base) => {
    adopt(current);
    void submit(current);
  };
  const takeTheirs = (current: Base) => {
    adopt(current);
    setDraft(current.saved);
    setStatus({ kind: "idle" });
  };
  const conflictWith = status.kind === "conflict" && status.current !== "loading" ? status.current : null;
  const keepMineBlocked =
    conflictWith === null
      ? null
      : uploading
        ? "Wait for the attachment to finish."
        : editing.body_change_needs_confirmation && draft.body !== conflictWith.saved.body && !nonMaterial
          ? "Confirm below that your change does not alter what was decided."
          : null;

  useEffect(() => {
    function handleKey(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") {
        event.preventDefault();
        void save();
      }
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [save]);

  const pages = useMemo(() => (nav ? linkablePages(nav.record_index) : null), [nav]);

  const update = <K extends keyof Draft>(field: K) => (value: Draft[K]) => {
    setDraft((current) => ({ ...current, [field]: value }));
    if (status.kind === "saved" || status.kind === "failed") setStatus({ kind: "idle" });
  };

  return (
    <div className="mx-auto w-full max-w-[860px] px-6 py-10 sm:px-10">
      <Breadcrumb items={[...record.breadcrumb, { label: record.title, href: `/r/${record.id}` }]} current="Edit" />

      <div className="sticky top-[calc(49px_+_var(--frame-top))] z-20 -mx-2 mb-6 flex flex-wrap items-center gap-3 border-b border-(--color-border) bg-(--color-bg) px-2 py-2.5">
        <h1 className="kos-heading mr-auto">Editing</h1>
        <span className="text-sm text-(--color-text-faint)" aria-live="polite">
          {status.kind === "saving" && "Saving…"}
          {status.kind === "saved" && !dirty && `Saved ${status.at.toLocaleTimeString()}`}
          {status.kind !== "saving" && dirty && (uploading ? "Attaching a file…" : "Unsaved changes")}
        </span>
        <SecondaryButton onClick={onClose}>Close</SecondaryButton>
        <PrimaryButton onClick={() => void save()} disabled={!canSave}>
          Save
        </PrimaryButton>
      </div>

      {status.kind === "conflict" && status.current === "loading" && (
        <Callout tone="danger">This page changed while you were editing. Loading the current version…</Callout>
      )}
      {status.kind === "conflict" && status.current === null && (
        <ConflictCallout onReload={onReload} onKeepEditing={() => setStatus({ kind: "idle" })} />
      )}
      {conflictWith && (
        <ConflictComparison
          theirs={conflictWith.saved.body}
          mine={draft.body}
          changedFields={Object.keys(metadataChanges(conflictWith.saved, draft)).map((field) => FIELD_LABELS[field])}
          keepMineBlocked={keepMineBlocked}
          onKeepMine={() => keepMine(conflictWith)}
          onTakeTheirs={() => takeTheirs(conflictWith)}
        />
      )}
      {status.kind === "failed" && <WriteFailureCallout failure={status.failure} />}
      {status.kind === "saved" && status.indexError && (
        <Callout>
          Saved, but search could not be refreshed: {status.indexError}
        </Callout>
      )}

      <div className="space-y-4">
        <Field label="Title">
          <input
            className={`${inputClass} font-serif text-[18px] font-semibold`}
            value={draft.title}
            onChange={(event) => update("title")(event.target.value)}
          />
        </Field>
        <Field label="Description" hint="One or two sentences, shown under the title">
          <textarea
            className={`${inputClass} resize-y`}
            rows={2}
            value={draft.description}
            onChange={(event) => update("description")(event.target.value)}
          />
        </Field>
        <Field label="Tags" hint="Comma separated">
          <input className={inputClass} value={draft.tags} onChange={(event) => update("tags")(event.target.value)} />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <PagePicker
            label="Related pages"
            hint="Pages worth reading alongside this one"
            value={draft.related}
            onChange={update("related")}
            pages={pages}
            selfId={record.id}
          />
          <PagePicker
            label="Based on"
            hint="Pages this one builds on"
            value={draft.sources}
            onChange={update("sources")}
            pages={pages}
            selfId={record.id}
          />
        </div>

        {editing.body_change_needs_confirmation && (
          <Callout>
            <p>
              This decision is in force. Only editorial fixes (wording, typos, links) can be made here. To change what
              was decided, propose a replacement from the decision's page instead.
            </p>
            {bodyChanged && (
              <label className="mt-2 flex items-center gap-2 text-(--color-text)">
                <input
                  type="checkbox"
                  className="accent-(--color-accent)"
                  checked={nonMaterial}
                  onChange={(event) => setNonMaterial(event.target.checked)}
                />
                This change does not alter what was decided.
              </label>
            )}
          </Callout>
        )}

        <MarkdownEditor
          value={draft.body}
          onChange={update("body")}
          path={editing.path}
          attachTo={{ record_id: record.id }}
          onUploadingChange={setUploading}
        />
      </div>

      <UnsavedChangesDialog blocker={blocker} save={{ save, canSave }} />
    </div>
  );
}
