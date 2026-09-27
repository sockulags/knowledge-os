import { useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router";
import { api } from "../api/client";
import type { PageTemplate, TemplatesPayload, WriteFailure } from "../api/types";
import { interfaceReference, write } from "../api/write";
import { useApi } from "../hooks/useApi";
import { useUnsavedChanges } from "../hooks/useUnsavedChanges";
import { useShell } from "../components/Shell";
import { PageSkeleton } from "../components/Skeleton";
import { Breadcrumb } from "../components/Breadcrumb";
import { EmptyState } from "../components/EmptyState";
import { Callout, LoadError } from "../components/Callout";
import { loadErrorMessage } from "../lib/language";
import { useDocumentTitle } from "../hooks/useDocumentTitle";
import { MarkdownEditor } from "../components/MarkdownEditor";
import { WriteFailureCallout } from "../components/WriteFailureCallout";
import { ConfirmDialog } from "../components/ConfirmDialog";
import {
  Field,
  PrimaryButton,
  SecondaryButton,
  UnsavedChangesDialog,
  inputClass,
  parseList,
} from "../components/EditorParts";

/** "Écrire une Note!" -> "ecrire-une-note": the lowercase kebab-case id the
 * core requires, which is also the file name. */
export function slugify(title: string): string {
  return title
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function cleanFolder(folder: string): string {
  return folder
    .split("/")
    .map((part) => part.trim())
    .filter((part) => part.length > 0)
    .join("/");
}

/** Create a page in a project: an ordinary note (written directly, in force)
 * or a decision (always a proposal until someone accepts it), started from a
 * template (`?template=<name>` picks one). Opened with
 * `?kind=decision&supersedes=<id>` it proposes a replacement for that
 * decision. */
export function NewRecord() {
  const { projectId } = useParams<{ projectId: string }>();
  const [params] = useSearchParams();
  const { nav } = useShell();
  const apiState = useApi(() => api.project(projectId!), [projectId]);
  const { data, loading, notFound } = apiState;
  useDocumentTitle(nav?.workspace_name, data ? `New page in ${data.title}` : null);

  if (loading) return <PageSkeleton />;
  if (notFound)
    return <EmptyState title="Project not found" body={`No project named "${projectId}" exists in this workspace.`} />;
  if (apiState.error || !data)
    return <LoadError>{loadErrorMessage(apiState, nav?.language, "Could not load this project.")}</LoadError>;

  return (
    <NewRecordForm
      projectId={data.id}
      projectTitle={data.title}
      breadcrumb={[...data.breadcrumb, { label: data.title, href: `/p/${data.id}` }]}
      initialFolder={params.get("folder") ?? ""}
      askedForDecision={params.get("kind") === "decision"}
      initialTemplate={params.get("template")}
      supersedes={params.get("supersedes")}
    />
  );
}

function NewRecordForm({
  projectId,
  projectTitle,
  breadcrumb,
  initialFolder,
  askedForDecision,
  initialTemplate,
  supersedes,
}: {
  projectId: string;
  projectTitle: string;
  breadcrumb: { label: string; href: string }[];
  initialFolder: string;
  askedForDecision: boolean;
  initialTemplate: string | null;
  supersedes: string | null;
}) {
  const navigate = useNavigate();
  const { refreshNav } = useShell();
  const [title, setTitle] = useState("");
  const [id, setId] = useState("");
  const [idEdited, setIdEdited] = useState(false);
  const [folder, setFolder] = useState(initialFolder);
  const [tags, setTags] = useState("");
  const [related, setRelated] = useState("");
  const [body, setBody] = useState("");
  const [saving, setSaving] = useState(false);
  const [failure, setFailure] = useState<WriteFailure | null>(null);
  const templates = useApi(() => api.templates(), []);
  const [template, setTemplate] = useState<PageTemplate | null>(null);
  const [pendingTemplate, setPendingTemplate] = useState<PageTemplate | null>(null);

  // A replacement is always a decision; otherwise the template decides, and
  // until templates load, `?kind=decision` does.
  const isDecision = supersedes !== null || (template ? template.kind === "decision" : askedForDecision);
  const templateText = template?.body ?? "";

  // Start from the requested template, the decision template for
  // `?kind=decision`, or the blank page, once the list has loaded.
  useEffect(() => {
    if (!templates.data || template) return;
    const usable = usableTemplates(templates.data, supersedes !== null);
    const wanted = initialTemplate ?? (askedForDecision || supersedes ? "decision" : "blank");
    const chosen =
      usable.find((item) => item.name === wanted) ??
      (askedForDecision || supersedes ? usable.find((item) => item.kind === "decision") : undefined) ??
      usable[0];
    if (!chosen) return;
    setTemplate(chosen);
    setBody((current) => (current.trim() === "" ? chosen.body : current));
  }, [templates.data, template, initialTemplate, askedForDecision, supersedes]);

  function chooseTemplate(next: PageTemplate) {
    if (next.name === template?.name) return;
    // Replacing text the person wrote needs a yes; the untouched text of the
    // previous template does not.
    if (body.trim() !== "" && body !== templateText) {
      setPendingTemplate(next);
      return;
    }
    setTemplate(next);
    setBody(next.body);
  }

  const replaced = useApi(() => (supersedes ? api.record(supersedes) : Promise.resolve(null)), [supersedes]);
  const effectiveId = idEdited ? id : slugify(title);
  const dirty =
    title.trim() !== "" ||
    (body.trim() !== "" && body !== templateText) ||
    tags.trim() !== "" ||
    related.trim() !== "";
  const { blocker, allowNextNavigation } = useUnsavedChanges(dirty && !saving);
  const canSave = title.trim() !== "" && effectiveId !== "" && body.trim() !== "" && !saving;

  async function create() {
    if (!canSave) return;
    setSaving(true);
    setFailure(null);
    const now = new Date();
    const tagList = parseList(tags);
    const relatedList = parseList(related);
    const metadata: Record<string, unknown> = {
      id: effectiveId,
      title: title.trim(),
      type: "project",
      ...(isDecision ? { record_kind: "decision" } : {}),
      // Notes are written directly; a decision is only ever a proposal here.
      status: isDecision ? "draft" : "active",
      scope: `project:${projectId}`,
      ...(tagList.length > 0 ? { tags: tagList } : {}),
      ...(relatedList.length > 0 ? { related: relatedList } : {}),
      ...(supersedes ? { supersedes: [supersedes] } : {}),
      provenance: [
        {
          kind: "interface-authored",
          reference: interfaceReference("create", now),
          captured: now.toISOString().replace(/\.\d{3}Z$/, "Z"),
        },
      ],
    };
    const cleaned = cleanFolder(folder);
    const outcome = await write.create({
      metadata,
      body: body.endsWith("\n") ? body : `${body}\n`,
      ...(cleaned ? { project_path: `${cleaned}/${effectiveId}.md` } : {}),
    });
    if (outcome.ok) {
      allowNextNavigation();
      refreshNav();
      navigate(`/r/${outcome.data.id}`);
    } else {
      setSaving(false);
      setFailure(outcome.failure);
    }
  }

  const heading = supersedes ? "Propose a replacement" : isDecision ? "New decision" : "New page";

  return (
    <div className="mx-auto w-full max-w-[860px] px-6 py-10 sm:px-10">
      <Breadcrumb items={breadcrumb} current={heading} />

      <div className="sticky top-[calc(49px_+_var(--frame-top))] z-20 -mx-2 mb-6 flex flex-wrap items-center gap-3 border-b border-(--color-border) bg-(--color-bg) px-2 py-2.5">
        <h1 className="kos-heading mr-auto">{heading}</h1>
        <SecondaryButton onClick={() => navigate(-1)}>Cancel</SecondaryButton>
        <PrimaryButton onClick={() => void create()} disabled={!canSave}>
          {saving ? "Creating…" : isDecision ? "Create proposal" : "Create page"}
        </PrimaryButton>
      </div>

      {isDecision && (
        <Callout>
          {supersedes ? (
            <>
              This creates a proposal to replace{" "}
              <strong>{replaced.data?.title ?? supersedes}</strong>. The current decision stays in force until the
              proposal is accepted as its replacement.
            </>
          ) : (
            <>This creates a proposal. It does not govern anything until someone accepts it.</>
          )}
        </Callout>
      )}
      {failure && <WriteFailureCallout failure={failure} />}

      <div className="space-y-4">
        {templates.data && (
          <TemplatePicker
            payload={templates.data}
            chosen={template}
            decisionsOnly={supersedes !== null}
            onChoose={chooseTemplate}
          />
        )}
        <Field label="Title">
          <input
            className={`${inputClass} font-serif text-[18px] font-semibold`}
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder={isDecision ? "What is being decided" : "Page title"}
            autoFocus
          />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Page id" hint="Lowercase words joined by hyphens; also the file name. Cannot be changed later.">
            <input
              className={`${inputClass} font-mono`}
              value={effectiveId}
              onChange={(event) => {
                setIdEdited(true);
                setId(event.target.value);
              }}
            />
          </Field>
          <Field label="Folder" hint={`Inside ${projectTitle}. Leave empty for the top level.`}>
            <input className={`${inputClass} font-mono`} value={folder} onChange={(event) => setFolder(event.target.value)} />
          </Field>
          <Field label="Tags" hint="Comma separated">
            <input className={inputClass} value={tags} onChange={(event) => setTags(event.target.value)} />
          </Field>
          <Field label="Related pages" hint="Page ids, comma separated">
            <input className={inputClass} value={related} onChange={(event) => setRelated(event.target.value)} />
          </Field>
        </div>
        <MarkdownEditor value={body} onChange={setBody} />
      </div>

      <UnsavedChangesDialog blocker={blocker} />
      {pendingTemplate && templates.data && (
        <ConfirmDialog
          title={templates.data.language.replace_title}
          confirmLabel={templates.data.language.replace_confirm}
          cancelLabel={templates.data.language.replace_cancel}
          onConfirm={() => {
            setTemplate(pendingTemplate);
            setBody(pendingTemplate.body);
            setPendingTemplate(null);
          }}
          onCancel={() => setPendingTemplate(null)}
        >
          {templates.data.language.replace_body.replace("{title}", pendingTemplate.title)}
        </ConfirmDialog>
      )}
    </div>
  );
}

/** The templates a page can start from: every one that can be used, and only
 * decision templates for a proposed replacement. */
function usableTemplates(payload: TemplatesPayload, decisionsOnly: boolean): PageTemplate[] {
  return payload.templates.filter((item) => item.error === null && (!decisionsOnly || item.kind === "decision"));
}

function TemplatePicker({
  payload,
  chosen,
  decisionsOnly,
  onChoose,
}: {
  payload: TemplatesPayload;
  chosen: PageTemplate | null;
  decisionsOnly: boolean;
  onChoose: (template: PageTemplate) => void;
}) {
  const { language } = payload;
  const shown = payload.templates.filter((item) => !decisionsOnly || item.kind === "decision");
  if (shown.length < 2) return null;
  return (
    <fieldset>
      <legend className="mb-1.5 block text-[13px] font-medium text-(--color-text-muted)">{language.label}</legend>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4" role="radiogroup" aria-label={language.label}>
        {shown.map((item) => {
          const selected = chosen?.name === item.name;
          const unusable = item.error !== null;
          const origin = item.path ? language.own.replace("{path}", item.path) : language.built_in;
          return (
            <button
              key={item.name}
              type="button"
              role="radio"
              aria-checked={selected}
              disabled={unusable}
              title={unusable ? language.unusable.replace("{error}", item.error ?? "") : origin}
              onClick={() => onChoose(item)}
              className={`flex flex-col items-start justify-start rounded-md border px-3 py-2 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-55 ${
                selected
                  ? "border-(--color-accent) bg-(--color-accent-ink-bg)"
                  : "border-(--color-border) hover:border-(--color-border-strong)"
              }`}
            >
              <span className="block text-sm font-medium text-(--color-text)">{item.title}</span>
              <span className="mt-0.5 block text-xs leading-snug text-(--color-text-faint)">
                {unusable ? language.unusable.replace("{error}", item.error ?? "") : item.description}
              </span>
            </button>
          );
        })}
      </div>
      <p className="mt-1.5 text-xs text-(--color-text-faint)">{language.hint}</p>
    </fieldset>
  );
}
