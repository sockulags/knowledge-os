import { useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router";
import { api } from "../api/client";
import type { PageTemplate, TemplatesPayload, WriteFailure } from "../api/types";
import { interfaceReference, isProposed, write } from "../api/write";
import { useApi } from "../hooks/useApi";
import { useUnsavedChanges } from "../hooks/useUnsavedChanges";
import { useShell } from "../components/Shell";
import { PageSkeleton } from "../components/Skeleton";
import { Breadcrumb } from "../components/Breadcrumb";
import { EmptyState } from "../components/EmptyState";
import { Callout, LoadError } from "../components/Callout";
import { kebab } from "../lib/text";
import { loadErrorMessage } from "../lib/language";
import { useDocumentTitle } from "../hooks/useDocumentTitle";
import { MarkdownEditor } from "../components/MarkdownEditor";
import { WriteFailureCallout } from "../components/WriteFailureCallout";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { Bot, Loader2 } from "lucide-react";
import { agentBridge } from "../lib/agentBridge";
import { agentStore, useAgent } from "../lib/agentStore";
import {
  Field,
  PrimaryButton,
  fieldLabelClass,
  SecondaryButton,
  UnsavedChangesDialog,
  inputClass,
  parseList,
} from "../components/EditorParts";

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
      place={{ kind: "project", projectId: data.id, projectTitle: data.title, initialFolder: params.get("folder") ?? "" }}
      breadcrumb={[...data.breadcrumb, { label: data.title, href: `/p/${data.id}` }]}
      askedForDecision={params.get("kind") === "decision"}
      initialTemplate={params.get("template")}
      supersedes={params.get("supersedes")}
    />
  );
}

/** The kinds of general page, outside any project: each has its own folder. */
const GENERAL_TYPES = [
  { type: "knowledge", label: "Knowledge", hint: "Saved in knowledge/: what holds across projects." },
  { type: "memory", label: "Memory", hint: "Saved in memory/: preferences and lessons to keep in mind." },
] as const;
type GeneralType = (typeof GENERAL_TYPES)[number]["type"];

/** Create a page outside any project, in knowledge/ or (`?type=memory`)
 * memory/. It is always an ordinary page; decisions belong to a project. */
export function NewGeneralPage() {
  const [params] = useSearchParams();
  const { nav } = useShell();
  useDocumentTitle(nav?.workspace_name, "New general page");
  return (
    <NewRecordForm
      place={{ kind: "general", initialType: params.get("type") === "memory" ? "memory" : "knowledge" }}
      breadcrumb={[]}
      askedForDecision={false}
      initialTemplate={params.get("template")}
      supersedes={null}
    />
  );
}

/** Where the new page goes: a folder of a project, or a general page. */
type Place =
  | { kind: "project"; projectId: string; projectTitle: string; initialFolder: string }
  | { kind: "general"; initialType: GeneralType };

function NewRecordForm({
  place,
  breadcrumb,
  askedForDecision,
  initialTemplate,
  supersedes,
}: {
  place: Place;
  breadcrumb: { label: string; href: string }[];
  askedForDecision: boolean;
  initialTemplate: string | null;
  supersedes: string | null;
}) {
  const navigate = useNavigate();
  const { refreshNav, nav } = useShell();
  const projectId = place.kind === "project" ? place.projectId : null;
  const [title, setTitle] = useState("");
  const [id, setId] = useState("");
  const [idEdited, setIdEdited] = useState(false);
  const [folder, setFolder] = useState(place.kind === "project" ? place.initialFolder : "");
  const [generalType, setGeneralType] = useState<GeneralType>(place.kind === "general" ? place.initialType : "knowledge");
  const [tags, setTags] = useState("");
  const [related, setRelated] = useState("");
  const [body, setBody] = useState("");
  const [saving, setSaving] = useState(false);
  const [failure, setFailure] = useState<WriteFailure | null>(null);
  // Attached files are stored next to the page, so once one is linked the
  // folder cannot change without breaking the link.
  const [folderLocked, setFolderLocked] = useState(false);
  const templates = useApi(() => api.templates(), []);
  const [template, setTemplate] = useState<PageTemplate | null>(null);
  const [pendingTemplate, setPendingTemplate] = useState<PageTemplate | null>(null);

  // A replacement is always a decision; otherwise the template decides, and
  // until templates load, `?kind=decision` does. A general page never is one.
  const notesOnly = projectId === null;
  const isDecision =
    !notesOnly && (supersedes !== null || (template ? template.kind === "decision" : askedForDecision));
  const templateText = template?.body ?? "";

  // Start from the requested template, the decision template for
  // `?kind=decision`, or the blank page, once the list has loaded.
  useEffect(() => {
    if (!templates.data || template) return;
    const usable = usableTemplates(templates.data, supersedes !== null, notesOnly);
    const wanted = initialTemplate ?? (askedForDecision || supersedes ? "decision" : "blank");
    const chosen =
      usable.find((item) => item.name === wanted) ??
      (askedForDecision || supersedes ? usable.find((item) => item.kind === "decision") : undefined) ??
      usable[0];
    if (!chosen) return;
    setTemplate(chosen);
    setBody((current) => (current.trim() === "" ? chosen.body : current));
  }, [templates.data, template, initialTemplate, askedForDecision, supersedes, notesOnly]);

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
  const effectiveId = idEdited ? id : kebab(title, null);
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
      type: projectId === null ? generalType : "project",
      ...(isDecision ? { record_kind: "decision" } : {}),
      // Notes are written directly; a decision is only ever a proposal here.
      status: isDecision ? "draft" : "active",
      scope: projectId === null ? "general" : `project:${projectId}`,
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
    const cleaned = projectId === null ? "" : cleanFolder(folder);
    const outcome = await write.create({
      metadata,
      body: body.endsWith("\n") ? body : `${body}\n`,
      ...(cleaned ? { project_path: `${cleaned}/${effectiveId}.md` } : {}),
    });
    if (outcome.ok) {
      allowNextNavigation();
      refreshNav();
      // Held back by the review rules: show the proposed change instead.
      navigate(isProposed(outcome.data) ? `/c/${outcome.data.proposal.id}` : `/r/${outcome.data.id}`);
    } else {
      setSaving(false);
      setFailure(outcome.failure);
    }
  }

  const heading = supersedes
    ? "Propose a replacement"
    : isDecision
      ? "New decision"
      : projectId === null
        ? "New general page"
        : "New page";
  const pagePath =
    projectId === null
      ? `${generalType}/${effectiveId || "new-page"}.md`
      : `projects/${projectId}/${cleanFolder(folder) ? `${cleanFolder(folder)}/` : ""}${effectiveId || "new-page"}.md`;

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
        {!supersedes && agentBridge() !== null && (
          <StartWithAgent
            context={{
              workspaceName: nav?.workspace_name ?? null,
              page: null,
              project: place.kind === "project" ? { id: place.projectId, title: place.projectTitle } : null,
            }}
            replacesText={body.trim() !== "" && body !== templateText}
            onDraft={(draft) => {
              if (draft.title) {
                setTitle(draft.title);
              }
              if (draft.body) setBody(draft.body);
            }}
          />
        )}
        {templates.data && (
          <TemplatePicker
            payload={templates.data}
            chosen={template}
            decisionsOnly={supersedes !== null}
            notesOnly={notesOnly}
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
          {place.kind === "project" ? (
            <Field
              label="Folder"
              hint={
                folderLocked
                  ? "Files are attached in this folder, so the page is created here."
                  : `Inside ${place.projectTitle}. Leave empty for the top level.`
              }
            >
              <input
                className={`${inputClass} font-mono`}
                value={folder}
                readOnly={folderLocked}
                onChange={(event) => setFolder(event.target.value)}
              />
            </Field>
          ) : (
            <fieldset>
              <legend className={fieldLabelClass}>Kind</legend>
              <div className="flex gap-4">
                {GENERAL_TYPES.map((item) => (
                  <label key={item.type} className="flex items-center gap-1.5 text-sm text-(--color-text)">
                    <input
                      type="radio"
                      name="general-type"
                      className="accent-(--color-accent)"
                      checked={generalType === item.type}
                      onChange={() => setGeneralType(item.type)}
                    />
                    {item.label}
                  </label>
                ))}
              </div>
              <span className="mt-1.5 block text-xs text-(--color-text-faint)">
                {GENERAL_TYPES.find((item) => item.type === generalType)!.hint}
              </span>
            </fieldset>
          )}
          <Field label="Tags" hint="Comma separated">
            <input className={inputClass} value={tags} onChange={(event) => setTags(event.target.value)} />
          </Field>
          <Field label="Related pages" hint="Page ids, comma separated">
            <input className={inputClass} value={related} onChange={(event) => setRelated(event.target.value)} />
          </Field>
        </div>
        <MarkdownEditor
          value={body}
          onChange={(next) => {
            // A link into this folder's assets/ ties the page to the folder.
            if (!folderLocked && /\]\(assets\//.test(next)) setFolderLocked(true);
            setBody(next);
          }}
          path={pagePath}
          // A general page takes attachments once it exists, from its editor.
          attachTo={projectId === null ? undefined : { project: projectId, folder: cleanFolder(folder) }}
        />
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

/** The templates a page can start from: every one that can be used, only
 * decision templates for a proposed replacement, and no decision template
 * for a general page. */
function usableTemplates(payload: TemplatesPayload, decisionsOnly: boolean, notesOnly: boolean): PageTemplate[] {
  return payload.templates.filter((item) => item.error === null && fits(item, decisionsOnly, notesOnly));
}

function fits(item: PageTemplate, decisionsOnly: boolean, notesOnly: boolean): boolean {
  return (!decisionsOnly || item.kind === "decision") && (!notesOnly || item.kind !== "decision");
}

/** Ctrl+N's agent start: one line in, a drafted title and body out, which the
 * person then reviews and saves. The agent writes nothing itself. */
function StartWithAgent({
  context,
  replacesText,
  onDraft,
}: {
  context: Parameters<typeof agentStore.compose>[1];
  replacesText: boolean;
  onDraft: (draft: { title: string; body: string }) => void;
}) {
  const agent = useAgent();
  const [request, setRequest] = useState("");
  const [working, setWorking] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    void agentStore.refresh();
  }, []);

  const chosen = agent.providers?.find((item) => item.id === agent.providerId) ?? null;
  const ready = chosen !== null && chosen.state === "ready" && chosen.adapterInstalled;

  async function draft() {
    if (request.trim() === "" || working) return;
    if (replacesText && !window.confirm("Replace the text you have written with the agent's draft?")) return;
    setWorking(true);
    setMessage(null);
    const result = await agentStore.compose(request, context);
    setWorking(false);
    if (result === null || (result.title === "" && result.body === "")) {
      setMessage(agentStore.snapshot().error ?? "The agent did not return a draft. Open the agent panel (Ctrl+J) to see why.");
      return;
    }
    onDraft(result);
  }

  return (
    <div className="kos-card px-4 py-3">
      <label className="block">
        <span className="mb-1.5 flex items-center gap-1.5 text-[13px] font-medium text-(--color-text-muted)">
          <Bot size={14} />
          Start with the agent
        </span>
        <div className="flex gap-2">
          <input
            className={`${inputClass} min-w-0 flex-1`}
            value={request}
            onChange={(event) => setRequest(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                void draft();
              }
            }}
            placeholder={ready ? "Describe the page in one line" : "Set up the agent in the agent panel (Ctrl+J) first"}
            disabled={!ready || working}
          />
          <SecondaryButton onClick={() => void draft()}>
            {working ? <Loader2 size={14} className="animate-spin" /> : "Draft"}
          </SecondaryButton>
        </div>
      </label>
      <p className="mt-1.5 text-xs text-(--color-text-faint)">
        {message ?? "The agent drafts the title and text from the knowledge base; nothing is saved until you create the page."}
      </p>
    </div>
  );
}

function TemplatePicker({
  payload,
  chosen,
  decisionsOnly,
  notesOnly,
  onChoose,
}: {
  payload: TemplatesPayload;
  chosen: PageTemplate | null;
  decisionsOnly: boolean;
  notesOnly: boolean;
  onChoose: (template: PageTemplate) => void;
}) {
  const { language } = payload;
  const shown = payload.templates.filter((item) => fits(item, decisionsOnly, notesOnly));
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
