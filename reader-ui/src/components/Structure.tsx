import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router";
import { CheckCircle2, AlertTriangle, X } from "lucide-react";
import { api } from "../api/client";
import type { DeletePreview, NavPayload, StructureResult, TreeNode, WriteFailure } from "../api/types";
import { structure, type Outcome } from "../api/write";
import { hasUnsavedChanges } from "../hooks/useUnsavedChanges";
import { pendingActions } from "../lib/pendingStore";
import { folderDisplayName } from "../lib/text";
import { WriteFailureCallout } from "./WriteFailureCallout";
import { slugify } from "../pages/NewRecord";
import { ConfirmDialog } from "./ConfirmDialog";
import { fieldLabelClass, inputClass } from "./EditorParts";

/** Something in a project tree that can be dragged, moved, or renamed. */
export type TreeItem =
  | { kind: "page"; id: string; title: string; projectId: string; folder: string }
  | { kind: "folder"; projectId: string; path: string; title: string; hasPage: boolean }
  | { kind: "project"; projectId: string; title: string };

/** A place a page or folder can go: a project's top level (`folder` "") or a folder in it. */
export interface Place {
  projectId: string;
  folder: string;
  label: string;
}

interface Feedback {
  tone: "ok" | "error";
  text: string;
  failure?: WriteFailure;
}

interface StructureApi {
  dragging: TreeItem | null;
  setDragging: (item: TreeItem | null) => void;
  canDrop: (item: TreeItem, place: Place) => boolean;
  drop: (item: TreeItem, place: Place) => void;
  rename: (item: TreeItem, title: string) => Promise<boolean>;
  newProject: () => void;
  newFolder: (projectId: string, parent: string, parentLabel: string) => void;
  moveTo: (item: TreeItem) => void;
  /** Open the delete confirmation for a page or a folder. */
  remove: (item: TreeItem) => void;
  busy: boolean;
}

const StructureContext = createContext<StructureApi | null>(null);

export function useStructure(): StructureApi {
  const value = useContext(StructureContext);
  if (value === null) throw new Error("useStructure needs a StructureProvider");
  return value;
}

function parentOf(path: string): string {
  const index = path.lastIndexOf("/");
  return index === -1 ? "" : path.slice(0, index);
}

/** Whether moving `item` to `place` would change anything and is allowed at all. */
export function canMove(item: TreeItem, place: Place): boolean {
  if (item.kind === "project") return false;
  if (item.kind === "page") return place.projectId !== item.projectId || place.folder !== item.folder;
  if (place.projectId === item.projectId) {
    if (place.folder === item.path || place.folder.startsWith(`${item.path}/`)) return false;
    return place.folder !== parentOf(item.path);
  }
  return true;
}

/** Every place in every project a page or folder can be moved to, depth first. */
function allPlaces(nav: NavPayload | null): (Place & { depth: number; projectTitle: string })[] {
  const places: (Place & { depth: number; projectTitle: string })[] = [];
  for (const project of nav?.projects ?? []) {
    places.push({ projectId: project.id, folder: "", label: project.title, depth: 0, projectTitle: project.title });
    const walk = (node: TreeNode, depth: number) => {
      for (const child of node.children) {
        if (!child.in_project) continue;
        places.push({
          projectId: project.id,
          folder: child.path,
          label: child.overview?.title ?? folderDisplayName(child.name),
          depth,
          projectTitle: project.title,
        });
        walk(child, depth + 1);
      }
    };
    walk(project.tree, 1);
  }
  return places;
}

function projectTitle(nav: NavPayload | null, projectId: string): string {
  return nav?.projects.find((project) => project.id === projectId)?.title ?? projectId;
}

function commitNote(result: StructureResult): string {
  const commit = result.commit;
  if (!commit || commit.committed || commit.skipped === "not_a_repo" || commit.skipped === "nothing_to_commit") return "";
  return ` Saved, but not committed to Git: ${commit.detail ?? commit.skipped}`;
}

/** Owns everything that changes the shape of a knowledge base from the
 * interface: new projects and folders, renames, and moves by drag and drop
 * or the "Move to…" dialog. Every change goes through the core's structure
 * endpoints; `onChanged(reload)` refreshes the sidebar, and reloads the page
 * too when files it may show were moved or rewritten. */
export function StructureProvider({
  nav,
  onChanged,
  children,
}: {
  nav: NavPayload | null;
  onChanged: (reloadPage: boolean) => void;
  children: ReactNode;
}) {
  const navigate = useNavigate();
  const [dragging, setDragging] = useState<TreeItem | null>(null);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [crossing, setCrossing] = useState<{ item: TreeItem; place: Place } | null>(null);
  const [moving, setMoving] = useState<TreeItem | null>(null);
  const [creatingProject, setCreatingProject] = useState(false);
  const [creatingFolder, setCreatingFolder] = useState<{ projectId: string; parent: string; parentLabel: string } | null>(
    null,
  );
  const [deleting, setDeleting] = useState<TreeItem | null>(null);
  const location = useLocation();

  useEffect(() => {
    if (feedback?.tone !== "ok") return;
    const timer = window.setTimeout(() => setFeedback(null), 6000);
    return () => window.clearTimeout(timer);
  }, [feedback]);

  const report = useCallback(
    (outcome: Outcome<StructureResult>, success: (result: StructureResult) => string, reloadPage: boolean) => {
      if (outcome.ok) {
        setFeedback({ tone: "ok", text: success(outcome.data) + commitNote(outcome.data) });
        onChanged(reloadPage && !hasUnsavedChanges());
        return true;
      }
      setFeedback({ tone: "error", text: "Nothing was changed.", failure: outcome.failure });
      return false;
    },
    [onChanged],
  );

  /** Moves and renames rewrite files and reload the page, so they wait for
   * unsaved edits to be saved or discarded. */
  const guardUnsaved = useCallback(() => {
    if (!hasUnsavedChanges()) return true;
    setFeedback({
      tone: "error",
      text: "Save or discard the changes on this page first. Moving or renaming can change the file you are editing.",
    });
    return false;
  }, []);

  const pageSha = useCallback(async (id: string): Promise<string | null> => {
    try {
      const record = await api.record(id);
      return record.editing.content_sha256;
    } catch {
      return null;
    }
  }, []);

  const execute = useCallback(
    async (item: TreeItem, place: Place, allowScopeChange: boolean) => {
      if (item.kind === "project" || !guardUnsaved()) return false;
      setBusy(true);
      try {
        // A decision action still waiting for Undo is written first, so the
        // move reads the files as they will be.
        await pendingActions.flushAll();
        const where =
          place.projectId !== item.projectId && place.folder
            ? `${place.label} in ${projectTitle(nav, place.projectId)}`
            : place.label;
        if (item.kind === "page") {
          const sha = await pageSha(item.id);
          if (sha === null) {
            setFeedback({ tone: "error", text: `Could not read “${item.title}” before moving it. Nothing was changed.` });
            return false;
          }
          const outcome = await structure.movePage(item.id, sha, place.projectId, place.folder, allowScopeChange);
          return report(outcome, () => `Moved “${item.title}” to ${where}.`, true);
        }
        const outcome = await structure.moveFolder(item.projectId, {
          path: item.path,
          to_project: place.projectId,
          to_parent: place.folder,
          allow_scope_change: allowScopeChange,
        });
        return report(outcome, () => `Moved folder “${item.title}” to ${where}.`, true);
      } finally {
        setBusy(false);
      }
    },
    [guardUnsaved, nav, pageSha, report],
  );

  const drop = useCallback(
    (item: TreeItem, place: Place) => {
      setDragging(null);
      if (!canMove(item, place) || busy) return;
      if (place.projectId !== item.projectId) {
        setCrossing({ item, place });
        return;
      }
      void execute(item, place, false);
    },
    [busy, execute],
  );

  const rename = useCallback(
    async (item: TreeItem, title: string) => {
      const trimmed = title.trim();
      if (!trimmed || !guardUnsaved()) return false;
      setBusy(true);
      try {
        await pendingActions.flushAll();
        if (item.kind === "folder") {
          const name = slugify(trimmed);
          if (!name) {
            setFeedback({ tone: "error", text: "A folder name needs at least one letter or digit." });
            return false;
          }
          const outcome = await structure.moveFolder(item.projectId, {
            path: item.path,
            name,
            ...(item.hasPage ? { title: trimmed } : {}),
          });
          return report(outcome, () => `Renamed folder to “${trimmed}”.`, true);
        }
        const id = item.kind === "page" ? item.id : item.projectId;
        const sha = await pageSha(id);
        if (sha === null) {
          setFeedback({ tone: "error", text: `Could not read “${item.title}” before renaming it. Nothing was changed.` });
          return false;
        }
        const outcome = await structure.renamePage(id, sha, trimmed);
        return report(outcome, () => `Renamed “${item.title}” to “${trimmed}”.`, true);
      } finally {
        setBusy(false);
      }
    },
    [guardUnsaved, pageSha, report],
  );

  /** Delete what the dialog showed, then leave a page that no longer exists. */
  const confirmDelete = useCallback(
    async (item: TreeItem, preview: DeletePreview): Promise<Outcome<StructureResult>> => {
      setBusy(true);
      try {
        await pendingActions.flushAll();
        let outcome: Outcome<StructureResult>;
        if (item.kind === "folder") {
          outcome = await structure.deleteFolder(item.projectId, item.path, preview.expected);
        } else {
          // The page's hash as the dialog showed it, so a page that changed
          // since is refused rather than deleted unseen.
          outcome = await structure.deletePage(preview.id ?? "", preview.expected[preview.path] ?? "", preview.expected);
        }
        if (outcome.ok) {
          setDeleting(null);
          const gone = new Set(preview.records.map((record) => `/r/${record.id}`));
          const leaving = gone.has(location.pathname);
          setFeedback({ tone: "ok", text: preview.dialog.done + commitNote(outcome.data) });
          if (leaving) navigate(preview.project ? `/p/${preview.project}` : "/");
          onChanged(!leaving && !hasUnsavedChanges());
        }
        return outcome;
      } finally {
        setBusy(false);
      }
    },
    [location.pathname, navigate, onChanged],
  );

  const value = useMemo<StructureApi>(
    () => ({
      dragging,
      setDragging,
      canDrop: canMove,
      drop,
      rename,
      newProject: () => setCreatingProject(true),
      newFolder: (projectId, parent, parentLabel) => setCreatingFolder({ projectId, parent, parentLabel }),
      moveTo: (item) => setMoving(item),
      remove: (item) => {
        if (item.kind !== "project" && guardUnsaved()) setDeleting(item);
      },
      busy,
    }),
    [busy, dragging, drop, guardUnsaved, rename],
  );

  return (
    <StructureContext.Provider value={value}>
      {children}

      {crossing && (
        <CrossProjectDialog
          item={crossing.item}
          place={crossing.place}
          fromTitle={projectTitle(nav, crossing.item.projectId)}
          toTitle={projectTitle(nav, crossing.place.projectId)}
          busy={busy}
          onCancel={() => setCrossing(null)}
          onConfirm={async () => {
            await execute(crossing.item, crossing.place, true);
            setCrossing(null);
          }}
        />
      )}

      {moving && (
        <MoveDialog
          item={moving}
          nav={nav}
          busy={busy}
          onCancel={() => setMoving(null)}
          onMove={async (place) => {
            const crossesProjects = place.projectId !== moving.projectId;
            const done = await execute(moving, place, crossesProjects);
            if (done) setMoving(null);
          }}
        />
      )}

      {creatingProject && (
        <NameDialog
          title="New project"
          label="Project name"
          confirmLabel="Create project"
          hint={(slug) => (slug ? `Its folder will be projects/${slug}.` : "Use at least one letter or digit.")}
          busy={busy}
          onCancel={() => setCreatingProject(false)}
          onConfirm={async (name, slug) => {
            setBusy(true);
            const outcome = await structure.createProject(slug, name);
            setBusy(false);
            if (report(outcome, () => `Created project “${name}”.`, false)) {
              setCreatingProject(false);
              navigate(`/p/${slug}`);
            }
          }}
        />
      )}

      {creatingFolder && (
        <NameDialog
          title="New folder"
          label="Folder name"
          confirmLabel="Create folder"
          hint={(slug) =>
            slug
              ? `In ${creatingFolder.parentLabel}, as the folder ${slug}. The folder gets its own page, which you can write in later.`
              : "Use at least one letter or digit."
          }
          busy={busy}
          onCancel={() => setCreatingFolder(null)}
          onConfirm={async (name, slug) => {
            setBusy(true);
            const path = creatingFolder.parent ? `${creatingFolder.parent}/${slug}` : slug;
            const outcome = await structure.createFolder(creatingFolder.projectId, path, name);
            setBusy(false);
            if (report(outcome, () => `Created folder “${name}” in ${creatingFolder.parentLabel}.`, false)) {
              setCreatingFolder(null);
            }
          }}
        />
      )}

      {deleting && (
        <DeleteDialog
          item={deleting}
          busy={busy}
          onCancel={() => setDeleting(null)}
          onConfirm={(preview) => confirmDelete(deleting, preview)}
        />
      )}

      {feedback && <FeedbackToast feedback={feedback} onClose={() => setFeedback(null)} />}
    </StructureContext.Provider>
  );
}

function FeedbackToast({ feedback, onClose }: { feedback: Feedback; onClose: () => void }) {
  const failure = feedback.failure;
  const issues = failure?.issues ?? [];
  return (
    <div
      role={feedback.tone === "error" ? "alert" : "status"}
      className={`kos-overlay fixed bottom-4 right-4 z-50 w-[min(420px,calc(100vw-2rem))] rounded-(--radius-card) px-4 py-3 text-sm ${
        feedback.tone === "error"
          ? "border-[color-mix(in_srgb,var(--color-accent-red-text)_28%,transparent)] bg-(--color-accent-red-bg) text-(--color-accent-red-text)"
          : "text-(--color-text)"
      }`}
      data-testid="structure-feedback"
    >
      <div className="flex items-start gap-2.5">
        {feedback.tone === "error" ? (
          <AlertTriangle size={16} className="mt-0.5 shrink-0" />
        ) : (
          <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-(--color-accent-green-text)" />
        )}
        <div className="min-w-0 flex-1">
          <p className={failure ? "font-medium" : ""}>{feedback.text}</p>
          {failure && issues.length === 0 && <p className="mt-1 whitespace-pre-wrap break-words">{failure.detail}</p>}
          {issues.length > 0 && (
            <ul className="mt-1 space-y-1">
              {issues.map((issue, index) => (
                <li key={index}>
                  <span className="break-all font-mono text-xs opacity-90">{issue.path}</span>
                  <span className="block">{issue.message}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Dismiss"
          className="-m-0.5 shrink-0 rounded-[5px] p-0.5 opacity-70 transition-opacity hover:opacity-100"
        >
          <X size={15} />
        </button>
      </div>
    </div>
  );
}

function NameDialog({
  title,
  label,
  confirmLabel,
  hint,
  busy,
  onCancel,
  onConfirm,
}: {
  title: string;
  label: string;
  confirmLabel: string;
  hint: (slug: string) => string;
  busy: boolean;
  onCancel: () => void;
  onConfirm: (name: string, slug: string) => void;
}) {
  const [name, setName] = useState("");
  const slug = slugify(name);
  const ready = name.trim() !== "" && slug !== "" && !busy;
  return (
    <ConfirmDialog
      title={title}
      confirmLabel={confirmLabel}
      workingLabel="Creating…"
      busy={busy}
      confirmDisabled={!ready}
      onCancel={onCancel}
      onConfirm={() => ready && onConfirm(name.trim(), slug)}
    >
      <label className="block">
        <span className={fieldLabelClass}>{label}</span>
        <input
          className={inputClass}
          value={name}
          onChange={(event) => setName(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && ready) onConfirm(name.trim(), slug);
          }}
        />
      </label>
      <p className="mt-2 text-xs text-(--color-text-faint)">{hint(slug)}</p>
    </ConfirmDialog>
  );
}

function itemLabel(item: TreeItem): string {
  return item.kind === "folder" ? `the folder “${item.title}”` : `“${item.title}”`;
}

function ScopeExplanation({ item, fromTitle, toTitle }: { item: TreeItem; fromTitle: string; toTitle: string }) {
  const what = item.kind === "folder" ? "it and every page in it" : "it";
  return (
    <>
      <p>
        Moving {itemLabel(item)} from <strong>{fromTitle}</strong> to <strong>{toTitle}</strong> makes {what} part of{" "}
        {toTitle}.
      </p>
      <p className="mt-2">
        A decision governs only its own project, and agents working on {fromTitle} will no longer get the moved pages
        as context. Links to the moved pages are updated. A decision that replaces, or is replaced by, a decision that
        stays in {fromTitle} cannot move.
      </p>
    </>
  );
}

function CrossProjectDialog({
  item,
  place,
  fromTitle,
  toTitle,
  busy,
  onCancel,
  onConfirm,
}: {
  item: TreeItem;
  place: Place;
  fromTitle: string;
  toTitle: string;
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <ConfirmDialog
      title={`Move to ${toTitle}?`}
      confirmLabel={`Move to ${toTitle}`}
      workingLabel="Moving…"
      busy={busy}
      onCancel={onCancel}
      onConfirm={onConfirm}
    >
      <ScopeExplanation item={item} fromTitle={fromTitle} toTitle={toTitle} />
      {place.folder && (
        <p className="mt-2">
          It goes into <strong>{place.label}</strong>.
        </p>
      )}
    </ConfirmDialog>
  );
}

/** The keyboard way to move something: pick a destination from every
 * project's folders, then Move. Arrow keys move through the list. */
function MoveDialog({
  item,
  nav,
  busy,
  onCancel,
  onMove,
}: {
  item: TreeItem;
  nav: NavPayload | null;
  busy: boolean;
  onCancel: () => void;
  onMove: (place: Place) => void;
}) {
  const places = useMemo(() => allPlaces(nav), [nav]);
  const [selected, setSelected] = useState<number>(-1);
  const choice = selected >= 0 ? places[selected] : null;
  const allowed = choice !== null && canMove(item, choice);
  const crossing = choice !== null && choice.projectId !== item.projectId;

  function isCurrent(place: Place): boolean {
    if (item.kind === "page") return place.projectId === item.projectId && place.folder === item.folder;
    if (item.kind === "folder") return place.projectId === item.projectId && place.folder === parentOf(item.path);
    return false;
  }

  return (
    <ConfirmDialog
      title={`Move ${itemLabel(item)}`}
      confirmLabel={crossing ? `Move to ${choice?.projectTitle}` : "Move here"}
      workingLabel="Moving…"
      busy={busy}
      confirmDisabled={!allowed}
      onCancel={onCancel}
      onConfirm={() => choice && allowed && onMove(choice)}
    >
      <p className="mb-2">Choose where it should go.</p>
      <div
        role="radiogroup"
        aria-label="Destination"
        className="max-h-72 overflow-y-auto rounded-(--radius-card) border border-(--color-border) bg-(--color-bg) p-1"
      >
        {places.map((place, index) => {
          const disabled = !canMove(item, place);
          return (
            <label
              key={`${place.projectId}/${place.folder}`}
              className={`flex cursor-pointer items-center gap-2 rounded-(--radius-control) px-2 py-1.5 text-sm ${
                selected === index ? "bg-(--color-bg-active) text-(--color-text)" : "text-(--color-text)"
              } ${disabled ? "cursor-not-allowed opacity-50" : selected === index ? "" : "hover:bg-(--color-bg-hover)"}`}
              style={{ paddingLeft: `${0.5 + place.depth * 1}rem` }}
            >
              <input
                type="radio"
                name="move-destination"
                className="accent-(--color-accent)"
                checked={selected === index}
                disabled={disabled}
                onChange={() => setSelected(index)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !disabled) {
                    event.preventDefault();
                    onMove(place);
                  }
                }}
              />
              <span className={place.depth === 0 ? "font-medium" : ""}>{place.label}</span>
              {isCurrent(place) && <span className="text-xs text-(--color-text-faint)">(current)</span>}
            </label>
          );
        })}
      </div>
      {crossing && choice && (
        <div className="mt-3">
          <ScopeExplanation
            item={item}
            fromTitle={projectTitle(nav, item.projectId)}
            toTitle={choice.projectTitle}
          />
        </div>
      )}
      <p className="mt-2 text-xs text-(--color-text-faint)">
        Moving keeps the page ids, updates links that point at what moves, and is saved as one commit.
      </p>
    </ConfirmDialog>
  );
}

function PageList({ heading, pages }: { heading: string; pages: { id: string; title: string }[] }) {
  return (
    <div className="mt-3">
      <p>{heading}</p>
      <ul className="mt-1.5 max-h-40 space-y-0.5 overflow-y-auto rounded-(--radius-card) border border-(--color-border) bg-(--color-bg-sidebar) px-3.5 py-2">
        {pages.map((page) => (
          <li key={page.id} className="text-(--color-text)">
            {page.title}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** The one confirmation left for a destructive action: what exactly is
 * deleted, which pages refer to it and what happens to them, and why it
 * cannot be deleted when it cannot. Every word comes from the preview. */
function DeleteDialog({
  item,
  busy,
  onCancel,
  onConfirm,
}: {
  item: TreeItem;
  busy: boolean;
  onCancel: () => void;
  onConfirm: (preview: DeletePreview) => Promise<Outcome<StructureResult>>;
}) {
  const [preview, setPreview] = useState<DeletePreview | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [failure, setFailure] = useState<WriteFailure | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load =
      item.kind === "folder" ? api.folderDeletion(item.projectId, item.path) : api.pageDeletion(item.kind === "page" ? item.id : "");
    load
      .then((data) => !cancelled && setPreview(data))
      .catch((error: unknown) => !cancelled && setLoadError(error instanceof Error ? error.message : String(error)));
    return () => {
      cancelled = true;
    };
  }, [item]);

  const title = preview?.dialog.title ?? `Delete “${item.title}”?`;
  if (preview === null) {
    return (
      <ConfirmDialog title={title} confirmLabel="Delete" tone="danger" confirmDisabled onCancel={onCancel} onConfirm={() => undefined}>
        {loadError ? <p>{loadError}</p> : <p>Checking what refers to it…</p>}
      </ConfirmDialog>
    );
  }

  const dialog = preview.dialog;
  const pages = preview.kind === "folder" ? preview.records : [];
  return (
    <ConfirmDialog
      title={dialog.title}
      confirmLabel={dialog.confirm}
      hideConfirm={!preview.deletable}
      cancelLabel={preview.deletable ? dialog.cancel : dialog.close}
      workingLabel={dialog.working}
      tone="danger"
      busy={busy}
      confirmDisabled={!preview.deletable}
      onCancel={onCancel}
      onConfirm={async () => {
        setFailure(null);
        const outcome = await onConfirm(preview);
        if (!outcome.ok) setFailure(outcome.failure);
      }}
    >
      <div data-testid="delete-dialog">
        {preview.deletable && <p>{dialog.intro}</p>}
        {pages.length > 0 && (
          <ul className="mt-1.5 max-h-40 space-y-0.5 overflow-y-auto rounded-(--radius-card) border border-(--color-border) bg-(--color-bg-sidebar) px-3.5 py-2">
            {pages.map((page) => (
              <li key={page.id} className="text-(--color-text)">
                {page.title}
              </li>
            ))}
            {dialog.other_files && <li className="text-(--color-text-faint)">{dialog.other_files}</li>}
          </ul>
        )}
        {dialog.notes.map((note) => (
          <p key={note} className="mt-2">
            {note}
          </p>
        ))}
        {!preview.deletable ? (
          <div className="mt-3">
            <p className="font-medium text-(--color-text)">{dialog.blocked_heading}</p>
            <ul className="mt-1 list-disc space-y-1 pl-5">
              {preview.blockers.map((blocker) => (
                <li key={blocker}>{blocker}</li>
              ))}
            </ul>
          </div>
        ) : (
          <>
            {preview.cleaned.length > 0 && <PageList heading={dialog.cleaned_heading} pages={preview.cleaned} />}
            {preview.linked.length > 0 && <PageList heading={dialog.linked_heading} pages={preview.linked} />}
            {preview.cleaned.length === 0 && preview.linked.length === 0 && (
              <p className="mt-2">{dialog.nothing_refers}</p>
            )}
            <p className="mt-3 text-xs text-(--color-text-faint)">{dialog.history}</p>
          </>
        )}
        {failure && (
          <div className="mt-3">
            <WriteFailureCallout failure={failure} />
          </div>
        )}
      </div>
    </ConfirmDialog>
  );
}
