import { useEffect, useRef, useState, type DragEvent, type KeyboardEvent, type ReactNode } from "react";
import { Link, useLocation, useNavigate } from "react-router";
import { ChevronRight, FilePlus, Folder, FolderKanban, FolderPlus, MoreHorizontal, MoveRight, Pencil } from "lucide-react";
import type { NavProject, RecordSummary, TreeNode } from "../api/types";
import { iconFor } from "../lib/icons";
import { useStructure, type Place, type TreeItem } from "./Structure";

// The project tree in the sidebar and on a project page. Pages and folders
// can be dragged onto a folder or a project (or onto a page, meaning its
// folder); every row also has a menu with "New page here", "New folder",
// "Rename", and "Move to…", the keyboard way to do the same.

const rowClass = "group relative flex items-center rounded-md";

/** Drag handlers for one row, or nothing when the row cannot move. */
function useDragSource(item: TreeItem | null) {
  const { setDragging, busy } = useStructure();
  if (item === null || busy) return {};
  return {
    draggable: true,
    onDragStart: (event: DragEvent) => {
      event.stopPropagation();
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", item.title);
      setDragging(item);
    },
    onDragEnd: () => setDragging(null),
  };
}

/** Drop handlers for one row that stands for `place`, and whether a drag is over it. */
function useDropTarget(place: Place | null): { over: boolean; handlers: Record<string, (event: DragEvent) => void> } {
  const { dragging, canDrop, drop } = useStructure();
  const [over, setOver] = useState(false);
  const allowed = place !== null && dragging !== null && canDrop(dragging, place);
  useEffect(() => {
    if (dragging === null) setOver(false);
  }, [dragging]);
  return {
    over: over && allowed,
    handlers: {
      onDragOver: (event) => {
        if (!allowed) return;
        event.preventDefault();
        event.stopPropagation();
        event.dataTransfer.dropEffect = "move";
        if (!over) setOver(true);
      },
      onDragLeave: (event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setOver(false);
      },
      onDrop: (event) => {
        setOver(false);
        if (!allowed || dragging === null || place === null) return;
        event.preventDefault();
        event.stopPropagation();
        drop(dragging, place);
      },
    },
  };
}

interface MenuEntry {
  label: string;
  icon: ReactNode;
  onSelect: () => void;
}

/** The "…" button at the end of a row and its menu. Arrow keys move
 * between entries; Escape closes it. */
function RowMenu({ label, entries }: { label: string; entries: MenuEntry[] }) {
  const [open, setOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    menuRef.current?.querySelector<HTMLButtonElement>("button")?.focus();
    function close(event: MouseEvent) {
      if (!menuRef.current?.contains(event.target as Node) && event.target !== buttonRef.current) setOpen(false);
    }
    window.addEventListener("mousedown", close);
    return () => window.removeEventListener("mousedown", close);
  }, [open]);

  function onKeyDown(event: KeyboardEvent) {
    const items = Array.from(menuRef.current?.querySelectorAll<HTMLButtonElement>("button") ?? []);
    const index = items.indexOf(document.activeElement as HTMLButtonElement);
    if (event.key === "Escape") {
      event.stopPropagation();
      setOpen(false);
      buttonRef.current?.focus();
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      items[(index + 1) % items.length]?.focus();
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      items[(index - 1 + items.length) % items.length]?.focus();
    } else if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      items[index]?.click();
    } else if (event.key === "Tab") {
      setOpen(false);
    }
  }

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        aria-label={`More for ${label}`}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={(event) => {
          event.stopPropagation();
          setOpen((value) => !value);
        }}
        className={`ml-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-[5px] text-(--color-text-faint) transition-colors hover:bg-(--color-bg-hover) hover:text-(--color-text) focus-visible:opacity-100 ${
          open ? "opacity-100" : "opacity-0 group-hover:opacity-100"
        }`}
      >
        <MoreHorizontal size={14} />
      </button>
      {open && (
        <div
          ref={menuRef}
          role="menu"
          aria-label={label}
          onKeyDown={onKeyDown}
          className="kos-menu absolute right-0 top-full z-40 mt-1 w-52"
        >
          {entries.map((entry) => (
            <button
              key={entry.label}
              type="button"
              role="menuitem"
              onClick={(event) => {
                event.stopPropagation();
                setOpen(false);
                entry.onSelect();
              }}
              className="kos-menu-item"
            >
              <span className="text-(--color-text-faint)">{entry.icon}</span>
              {entry.label}
            </button>
          ))}
        </div>
      )}
    </>
  );
}

/** A title turned into a text field: Enter saves, Escape cancels, and
 * leaving the field saves a changed title. */
function RenameField({ initial, onDone }: { initial: string; onDone: (title: string | null) => Promise<void> | void }) {
  const [value, setValue] = useState(initial);
  const [saving, setSaving] = useState(false);
  const finished = useRef(false);
  const inputRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    inputRef.current?.focus();
    inputRef.current?.select();
  }, []);

  async function finish(save: boolean) {
    // Enter, Escape, and the blur that follows either must act only once.
    if (finished.current) return;
    finished.current = true;
    const title = value.trim();
    if (!save || title === "" || title === initial) {
      await onDone(null);
      return;
    }
    setSaving(true);
    await onDone(title);
  }

  return (
    <input
      ref={inputRef}
      aria-label="New name"
      value={value}
      disabled={saving}
      onChange={(event) => setValue(event.target.value)}
      onKeyDown={(event) => {
        if (event.key === "Enter") void finish(true);
        if (event.key === "Escape") {
          event.stopPropagation();
          void finish(false);
        }
      }}
      onBlur={() => void finish(true)}
      onClick={(event) => event.stopPropagation()}
      className="kos-input min-w-0 flex-1 px-1.5 py-0.5 text-sm"
    />
  );
}

function useRename(item: TreeItem | null) {
  const { rename } = useStructure();
  const [renaming, setRenaming] = useState(false);
  return {
    renaming,
    start: () => setRenaming(true),
    field: (initial: string) => (
      <RenameField
        initial={initial}
        onDone={async (title) => {
          if (title !== null && item !== null) await rename(item, title);
          setRenaming(false);
        }}
      />
    ),
  };
}

function ChevronButton({ open, onToggle, hidden }: { open: boolean; onToggle: () => void; hidden?: boolean }) {
  if (hidden) return <span className="w-5 shrink-0" />;
  return (
    <button
      type="button"
      onClick={onToggle}
      className="flex h-6 w-5 shrink-0 items-center justify-center rounded-[5px] text-(--color-text-faint) transition-colors hover:text-(--color-text)"
      aria-label={open ? "Collapse" : "Expand"}
      aria-expanded={open}
    >
      <ChevronRight size={13} className={open ? "rotate-90 transition-transform duration-100" : "transition-transform duration-100"} />
    </button>
  );
}

// A drop target under the pointer gets the ink tint and a dashed ink outline;
// the page being read gets the same tint without the outline.
const dropTargetClass =
  "bg-(--color-bg-active) text-(--color-text) outline-1 outline-dashed outline-offset-[-1px] outline-(--color-accent)";
const activeRowClass = "bg-(--color-bg-active) font-medium text-(--color-text) [&>svg]:text-(--color-accent-text) [&>svg]:opacity-100";

function linkClass(active: boolean, over: boolean): string {
  if (over) return dropTargetClass;
  return active ? activeRowClass : "text-(--color-text-muted) hover:bg-(--color-bg-hover) hover:text-(--color-text)";
}

/** One page: a link, draggable when it is a project page, and a drop target
 * that stands for the folder it is in. */
function PageRow({ record, projectId, folder, folderLabel }: { record: RecordSummary; projectId: string; folder: string; folderLabel: string }) {
  const location = useLocation();
  const structure = useStructure();
  const movable = record.type === "project";
  const item: TreeItem | null = movable
    ? { kind: "page", id: record.id, title: record.title, projectId, folder }
    : null;
  const drag = useDragSource(item);
  const target = useDropTarget({ projectId, folder, label: folderLabel });
  const { renaming, start, field } = useRename(item);
  const href = `/r/${record.id}`;
  const Icon = iconFor(record.type, record.is_decision);
  const dragged = structure.dragging?.kind === "page" && structure.dragging.id === record.id;

  return (
    <div className={`${rowClass} ${dragged ? "opacity-50" : ""}`} {...drag} {...target.handlers} data-tree-page={record.id}>
      {renaming ? (
        <div className="flex min-w-0 flex-1 items-center gap-2 px-2 py-0.5">
          <Icon size={14} className="shrink-0 opacity-70" />
          {field(record.title)}
        </div>
      ) : (
        <Link
          to={href}
          draggable={false}
          className={`flex min-w-0 flex-1 items-center gap-2 rounded-md px-2 py-1 text-sm ${linkClass(location.pathname === href, false)}`}
          title={record.title}
        >
          <Icon size={14} className="shrink-0 opacity-70" />
          <span className="truncate">{record.title}</span>
        </Link>
      )}
      {item !== null && !renaming && (
        <RowMenu
          label={record.title}
          entries={[
            { label: "Rename", icon: <Pencil size={14} />, onSelect: start },
            { label: "Move to…", icon: <MoveRight size={14} />, onSelect: () => structure.moveTo(item) },
          ]}
        />
      )}
    </div>
  );
}

function BrokenRows({ node }: { node: TreeNode }) {
  return (
    <>
      {node.broken.map((entry) => (
        <div key={entry.path} className="truncate px-2 py-1 text-xs text-(--color-accent-red-text)" title={entry.message}>
          {entry.path.split("/").pop()}
        </div>
      ))}
    </>
  );
}

/** What is inside one folder (or a project's top level): its pages, broken
 * files, and subfolders. */
export function TreeContents({ node, projectId, label, depth }: { node: TreeNode; projectId: string; label: string; depth: number }) {
  return (
    <>
      {node.records.map((record) => (
        <PageRow key={record.id} record={record} projectId={projectId} folder={node.path} folderLabel={label} />
      ))}
      <BrokenRows node={node} />
      {node.children.map((child) => (
        <FolderNode key={child.path || child.name} node={child} projectId={projectId} depth={depth} />
      ))}
    </>
  );
}

function containsPath(node: TreeNode, pathname: string): boolean {
  if (node.overview && `/r/${node.overview.id}` === pathname) return true;
  if (node.records.some((record) => `/r/${record.id}` === pathname)) return true;
  return node.children.some((child) => containsPath(child, pathname));
}

/** One folder: its own page (when it has one) or its name, a chevron, and
 * its contents. Dragging over a closed folder opens it after a moment. */
function FolderNode({ node, projectId, depth }: { node: TreeNode; projectId: string; depth: number }) {
  const location = useLocation();
  const navigate = useNavigate();
  const structure = useStructure();
  const holdsCurrentPage = containsPath(node, location.pathname);
  const [open, setOpen] = useState(depth < 1 || holdsCurrentPage);
  useEffect(() => {
    // Also after a move brings the open page into this folder.
    if (holdsCurrentPage) setOpen(true);
  }, [holdsCurrentPage]);
  const title = node.overview?.title ?? node.name;
  const item: TreeItem | null = node.in_project
    ? { kind: "folder", projectId, path: node.path, title, hasPage: node.overview !== null }
    : null;
  const drag = useDragSource(item);
  const target = useDropTarget(node.in_project ? { projectId, folder: node.path, label: title } : null);
  const { renaming, start, field } = useRename(item);
  const hasChildContent = node.records.length > 0 || node.children.length > 0 || node.broken.length > 0;
  const dragged = structure.dragging?.kind === "folder" && structure.dragging.projectId === projectId && structure.dragging.path === node.path;

  useEffect(() => {
    if (!target.over || open) return;
    const timer = window.setTimeout(() => setOpen(true), 600);
    return () => window.clearTimeout(timer);
  }, [target.over, open]);

  const href = node.overview ? `/r/${node.overview.id}` : null;
  const label = (
    <>
      <Folder size={14} className="shrink-0 opacity-70" />
      <span className={`truncate ${node.overview ? "" : "capitalize"}`}>{title}</span>
    </>
  );

  return (
    <div className={dragged ? "opacity-50" : ""}>
      <div className={rowClass} {...drag} {...target.handlers} data-tree-folder={`${projectId}/${node.path}`}>
        <ChevronButton open={open} onToggle={() => setOpen((value) => !value)} hidden={!hasChildContent && node.overview !== null} />
        {renaming ? (
          <div className="flex min-w-0 flex-1 items-center gap-2 px-2 py-0.5">
            <Folder size={14} className="shrink-0 opacity-70" />
            {field(title)}
          </div>
        ) : href ? (
          <Link
            to={href}
            draggable={false}
            className={`flex min-w-0 flex-1 items-center gap-2 rounded-md px-2 py-1 text-sm ${linkClass(location.pathname === href, target.over)}`}
            title={title}
          >
            {label}
          </Link>
        ) : (
          <span
            className={`flex min-w-0 flex-1 items-center gap-2 rounded-md px-2 py-1 text-sm ${linkClass(false, target.over)}`}
          >
            {label}
          </span>
        )}
        {item !== null && !renaming && (
          <RowMenu
            label={title}
            entries={[
              {
                label: "New page here",
                icon: <FilePlus size={14} />,
                onSelect: () => navigate(`/p/${projectId}/new?folder=${encodeURIComponent(node.path)}`),
              },
              {
                label: "New folder",
                icon: <FolderPlus size={14} />,
                onSelect: () => {
                  setOpen(true);
                  structure.newFolder(projectId, node.path, title);
                },
              },
              { label: "Rename", icon: <Pencil size={14} />, onSelect: start },
              { label: "Move to…", icon: <MoveRight size={14} />, onSelect: () => structure.moveTo(item) },
            ]}
          />
        )}
      </div>

      {open && hasChildContent && (
        <div className="ml-2.5 border-l border-(--color-border) pl-1.5">
          <TreeContents node={node} projectId={projectId} label={title} depth={depth + 1} />
        </div>
      )}
    </div>
  );
}

/** The menu entries a project offers: new page and folder at its top level,
 * and renaming it (its overview's title). */
function projectEntries(
  project: { id: string; title: string },
  navigate: (to: string) => void,
  structure: ReturnType<typeof useStructure>,
  startRename?: () => void,
): MenuEntry[] {
  return [
    { label: "New page here", icon: <FilePlus size={14} />, onSelect: () => navigate(`/p/${project.id}/new`) },
    {
      label: "New folder",
      icon: <FolderPlus size={14} />,
      onSelect: () => structure.newFolder(project.id, "", project.title),
    },
    ...(startRename ? [{ label: "Rename", icon: <Pencil size={14} />, onSelect: startRename }] : []),
  ];
}

/** A project's whole tree on its own page, inside a box that is itself the
 * drop target for the project's top level. */
export function ProjectPageTree({ projectId, projectTitle, tree }: { projectId: string; projectTitle: string; tree: TreeNode }) {
  const target = useDropTarget({ projectId, folder: "", label: projectTitle });
  return (
    <div
      {...target.handlers}
      className={`rounded-(--radius-card) border bg-(--color-bg-raised) p-2 transition-colors ${
        target.over ? "border-dashed border-(--color-accent) bg-(--color-bg-active)" : "border-(--color-border)"
      }`}
      data-tree-root={projectId}
    >
      <TreeContents node={tree} projectId={projectId} label={projectTitle} depth={0} />
    </div>
  );
}

/** One project in the sidebar: an expandable row that is also the drop
 * target for the project's top level. Starts expanded while the current
 * page is the project's own page or one of its pages. */
export function SidebarProject({ project }: { project: NavProject }) {
  const location = useLocation();
  const navigate = useNavigate();
  const structure = useStructure();
  const isActive = location.pathname === `/p/${project.id}` || containsPath(project.tree, location.pathname);
  const [open, setOpen] = useState(isActive);
  const target = useDropTarget({ projectId: project.id, folder: "", label: project.title });
  const item: TreeItem = { kind: "project", projectId: project.id, title: project.title };
  const { renaming, start, field } = useRename(item);
  useEffect(() => {
    if (isActive) setOpen(true);
  }, [isActive]);
  useEffect(() => {
    if (!target.over || open) return;
    const timer = window.setTimeout(() => setOpen(true), 600);
    return () => window.clearTimeout(timer);
  }, [target.over, open]);

  const hasContent = project.tree.records.length > 0 || project.tree.children.length > 0 || project.tree.broken.length > 0;
  const href = `/p/${project.id}`;

  return (
    <div>
      <div className={rowClass} {...target.handlers} data-tree-project={project.id}>
        <ChevronButton open={open} onToggle={() => setOpen((value) => !value)} hidden={!hasContent} />
        {renaming ? (
          <div className="flex min-w-0 flex-1 items-center gap-2 px-1 py-0.5">
            <FolderKanban size={14} className="shrink-0 opacity-70" />
            {field(project.title)}
          </div>
        ) : (
          <Link
            to={href}
            draggable={false}
            className={`flex min-w-0 flex-1 items-center gap-2 truncate rounded-md px-1.5 py-1 text-sm ${
              target.over ? dropTargetClass : location.pathname === href ? activeRowClass : "text-(--color-text) hover:bg-(--color-bg-hover)"
            }`}
          >
            <FolderKanban size={14} className="shrink-0 opacity-70" />
            <span className="truncate">{project.title}</span>
          </Link>
        )}
        {!renaming && <RowMenu label={project.title} entries={projectEntries(project, navigate, structure, start)} />}
      </div>
      {open && hasContent && (
        <div className="ml-2.5 border-l border-(--color-border) pl-1.5">
          <TreeContents node={project.tree} projectId={project.id} label={project.title} depth={1} />
        </div>
      )}
    </div>
  );
}
