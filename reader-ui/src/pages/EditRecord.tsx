import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { api } from "../api/client";
import type { EditableMetadata, RecordPayload, WriteFailure } from "../api/types";
import { interfaceReference, write } from "../api/write";
import { useApi } from "../hooks/useApi";
import { useUnsavedChanges } from "../hooks/useUnsavedChanges";
import { useShell } from "../components/Shell";
import { PageSkeleton } from "../components/Skeleton";
import { Breadcrumb } from "../components/Breadcrumb";
import { RecordNotFound } from "../components/EmptyState";
import { Callout } from "../components/Callout";
import { MarkdownEditor } from "../components/MarkdownEditor";
import { ConflictCallout, WriteFailureCallout } from "../components/WriteFailureCallout";
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
  tags: string;
  related: string;
  sources: string;
  body: string;
}

function draftFrom(metadata: EditableMetadata, body: string): Draft {
  return {
    title: metadata.title,
    tags: metadata.tags.join(", "),
    related: metadata.related.join(", "),
    sources: metadata.sources.join(", "),
    body,
  };
}

const LIST_FIELDS = ["tags", "related", "sources"] as const;

/** The fields that differ from the saved revision, as PATCH metadata
 * (an emptied list is removed rather than written as `[]`). */
function metadataChanges(saved: Draft, draft: Draft): Record<string, unknown> {
  const changes: Record<string, unknown> = {};
  if (draft.title.trim() !== saved.title) changes.title = draft.title.trim();
  for (const field of LIST_FIELDS) {
    const next = parseList(draft[field]);
    if (next.join(",") !== parseList(saved[field]).join(",")) changes[field] = next.length > 0 ? next : null;
  }
  return changes;
}

type Status =
  | { kind: "idle" }
  | { kind: "saving" }
  | { kind: "saved"; at: Date; indexError: string | null }
  | { kind: "conflict" }
  | { kind: "failed"; failure: WriteFailure };

export function EditRecord() {
  const { recordId } = useParams<{ recordId: string }>();
  const navigate = useNavigate();
  const { refreshNav, nav } = useShell();
  const [loadKey, setLoadKey] = useState(0);
  const { data, loading, notFound, error } = useApi(() => api.record(recordId!), [recordId, loadKey]);

  if (loading) return <PageSkeleton />;
  if (notFound) return <RecordNotFound nav={nav} recordId={recordId} />;
  if (error || !data) return <Callout tone="danger">{error ?? nav?.language.load_error ?? "Could not load this page."}</Callout>;
  if (!data.editing.editable || data.editing.metadata === null || data.editing.raw_body === null) {
    return (
      <div className="mx-auto w-full max-w-[720px] px-6 py-12 sm:px-10">
        <Callout>
          This kind of page cannot be edited here. <Link to={`/r/${data.id}`} className="underline">Back to the page</Link>
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
  const [saved, setSaved] = useState<Draft>(() => draftFrom(editing.metadata!, editing.raw_body!));
  const [draft, setDraft] = useState<Draft>(saved);
  const [sha, setSha] = useState(editing.content_sha256!);
  const [status, setStatus] = useState<Status>({ kind: "idle" });
  const [nonMaterial, setNonMaterial] = useState(false);

  const changes = metadataChanges(saved, draft);
  const bodyChanged = draft.body !== saved.body;
  const dirty = bodyChanged || Object.keys(changes).length > 0;
  const needsConfirmation = editing.body_change_needs_confirmation && bodyChanged;
  const { blocker } = useUnsavedChanges(dirty);

  const save = useCallback(async () => {
    if (!dirty || status.kind === "saving" || (needsConfirmation && !nonMaterial)) return;
    setStatus({ kind: "saving" });
    const outcome = await write.edit(record.id, {
      expected_sha256: sha,
      ...(Object.keys(changes).length > 0 ? { metadata: changes } : {}),
      ...(bodyChanged ? { body: draft.body } : {}),
      ...(needsConfirmation ? { confirm_non_material: true, change_reference: interfaceReference("edit") } : {}),
    });
    if (outcome.ok) {
      // The returned hash is the revision now on disk: the next save sends it.
      setSha(outcome.data.content_sha256);
      const next = { ...draft, title: draft.title.trim() };
      setSaved(next);
      setDraft(next);
      setNonMaterial(false);
      setStatus({ kind: "saved", at: new Date(), indexError: outcome.data.index.error });
      if ("title" in changes) refreshNav();
    } else if (outcome.failure.error === "conflict") {
      setStatus({ kind: "conflict" });
    } else {
      setStatus({ kind: "failed", failure: outcome.failure });
    }
  }, [dirty, status.kind, needsConfirmation, nonMaterial, record.id, sha, changes, bodyChanged, draft, refreshNav]);

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

  const update = (field: keyof Draft) => (value: string) => {
    setDraft((current) => ({ ...current, [field]: value }));
    if (status.kind === "saved" || status.kind === "failed") setStatus({ kind: "idle" });
  };

  return (
    <div className="mx-auto w-full max-w-[860px] px-6 py-10 sm:px-10">
      <Breadcrumb items={[...record.breadcrumb, { label: record.title, href: `/r/${record.id}` }]} current="Edit" />

      <div className="sticky top-[49px] z-20 -mx-2 mb-6 flex flex-wrap items-center gap-3 bg-(--color-bg) px-2 py-2">
        <h1 className="mr-auto text-lg font-semibold">Editing</h1>
        <span className="text-sm text-(--color-text-faint)" aria-live="polite">
          {status.kind === "saving" && "Saving…"}
          {status.kind === "saved" && !dirty && `Saved ${status.at.toLocaleTimeString()}`}
          {status.kind !== "saving" && dirty && "Unsaved changes"}
        </span>
        <SecondaryButton onClick={onClose}>Close</SecondaryButton>
        <PrimaryButton onClick={() => void save()} disabled={!dirty || status.kind === "saving" || (needsConfirmation && !nonMaterial)}>
          Save
        </PrimaryButton>
      </div>

      {status.kind === "conflict" && <ConflictCallout onReload={onReload} onKeepEditing={() => setStatus({ kind: "idle" })} />}
      {status.kind === "failed" && <WriteFailureCallout failure={status.failure} />}
      {status.kind === "saved" && status.indexError && (
        <Callout>
          Saved, but search could not be refreshed: {status.indexError}
        </Callout>
      )}

      <div className="space-y-4">
        <Field label="Title">
          <input className={`${inputClass} text-base font-medium`} value={draft.title} onChange={(event) => update("title")(event.target.value)} />
        </Field>
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Tags" hint="Comma separated">
            <input className={inputClass} value={draft.tags} onChange={(event) => update("tags")(event.target.value)} />
          </Field>
          <Field label="Related pages" hint="Page ids, comma separated">
            <input className={inputClass} value={draft.related} onChange={(event) => update("related")(event.target.value)} />
          </Field>
          <Field label="Based on" hint="Page ids, comma separated">
            <input className={inputClass} value={draft.sources} onChange={(event) => update("sources")(event.target.value)} />
          </Field>
        </div>

        {editing.body_change_needs_confirmation && (
          <Callout>
            <p>
              This decision is in force. Only editorial fixes (wording, typos, links) can be made here. To change what
              was decided, propose a replacement from the decision's page instead.
            </p>
            {bodyChanged && (
              <label className="mt-2 flex items-center gap-2 text-(--color-text)">
                <input type="checkbox" checked={nonMaterial} onChange={(event) => setNonMaterial(event.target.checked)} />
                This change does not alter what was decided.
              </label>
            )}
          </Callout>
        )}

        <MarkdownEditor value={draft.body} onChange={update("body")} path={editing.path} />
      </div>

      <UnsavedChangesDialog blocker={blocker} />
    </div>
  );
}
