import { useEffect, useState, type ReactNode } from "react";
import { Link, useLocation } from "react-router";
import { ChevronRight, Home, Inbox, LayoutGrid, Search, FolderKanban, BookOpen, FolderClosed } from "lucide-react";
import type { NavPayload, TreeNode } from "../api/types";
import { TreeNodeView } from "./ProjectTree";
import { SHORTCUT_KEYS } from "../lib/quickSwitch";

function NavRow({
  to,
  icon,
  label,
  active,
  count,
}: {
  to: string;
  icon: ReactNode;
  label: string;
  active: boolean;
  count?: number;
}) {
  return (
    <Link
      to={to}
      className={`flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-sm ${
        active ? "bg-(--color-bg-hover) font-medium" : "text-(--color-text-muted) hover:bg-(--color-bg-hover) hover:text-(--color-text)"
      }`}
    >
      {icon}
      <span className="flex-1">{label}</span>
      {count !== undefined && count > 0 && (
        <span
          className="min-w-5 rounded-full bg-(--color-accent-amber-bg) px-1.5 py-0.5 text-center text-xs font-medium leading-none text-(--color-accent-amber-text)"
          data-testid="decide-count"
        >
          {count}
        </span>
      )}
    </Link>
  );
}

function Section({
  title,
  defaultOpen = true,
  children,
}: {
  title: string;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="mt-5">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="mb-1 flex w-full items-center gap-1 px-1 text-xs font-semibold uppercase tracking-wide text-(--color-text-faint) hover:text-(--color-text-muted)"
      >
        <ChevronRight size={11} className={open ? "rotate-90 transition-transform" : "transition-transform"} />
        {title}
      </button>
      {open && <div className="space-y-0.5">{children}</div>}
    </div>
  );
}

export function Sidebar({
  nav,
  onNavigate,
  onOpenQuickFind,
}: {
  nav: NavPayload | null;
  onNavigate?: () => void;
  onOpenQuickFind: () => void;
}) {
  const location = useLocation();

  return (
    <div className="flex h-full flex-col overflow-y-auto px-3 py-4" onClick={onNavigate}>
      <Link to="/" className="mb-3 truncate px-2 text-sm font-semibold">
        {nav?.workspace_name ?? "Knowledge OS"}
      </Link>

      <button
        type="button"
        onClick={(event) => {
          event.stopPropagation();
          onOpenQuickFind();
        }}
        className="mb-3 flex items-center justify-between rounded-md border border-(--color-border) bg-(--color-bg) px-2.5 py-1.5 text-sm text-(--color-text-muted) hover:border-(--color-border-strong)"
      >
        <span className="flex items-center gap-2">
          <Search size={14} />
          Search
        </span>
        <kbd className="rounded border border-(--color-border) px-1.5 py-0.5 font-mono text-[10px] text-(--color-text-faint)">
          {SHORTCUT_KEYS}
        </kbd>
      </button>

      <nav className="space-y-0.5">
        <NavRow to="/" icon={<Home size={15} />} label="Home" active={location.pathname === "/"} />
        {nav && (
          <NavRow
            to="/decide"
            icon={<Inbox size={15} />}
            label={nav.decide.label}
            active={location.pathname === "/decide"}
            count={nav.decide.count}
          />
        )}
        <NavRow
          to="/everything"
          icon={<LayoutGrid size={15} />}
          label="Everything"
          active={location.pathname === "/everything"}
        />
        <NavRow to="/search" icon={<Search size={15} />} label="Search" active={location.pathname.startsWith("/search")} />
      </nav>

      <Section title="Projects">
        {nav?.projects.length ? (
          nav.projects.map((project) => <ProjectNode key={project.id} project={project} />)
        ) : (
          <p className="px-2 text-sm text-(--color-text-faint)">No project yet.</p>
        )}
      </Section>

      {nav && nav.skills.length > 0 && (
        <Section title="Skills" defaultOpen={false}>
          {nav.skills.map((skill) => (
            <Link
              key={skill.name}
              to={`/s/${skill.name}`}
              className={`flex items-center gap-2.5 truncate rounded-md px-2.5 py-1.5 text-sm ${
                location.pathname === `/s/${skill.name}` ? "bg-(--color-bg-hover) font-medium" : "text-(--color-text-muted) hover:bg-(--color-bg-hover) hover:text-(--color-text)"
              }`}
              title={skill.name}
            >
              <BookOpen size={14} className="shrink-0 opacity-70" />
              <span className="truncate">{skill.name}</span>
            </Link>
          ))}
        </Section>
      )}

      {nav && nav.repo_docs.length > 0 && (
        <Section title="Repository docs" defaultOpen={false}>
          {nav.repo_docs.map((doc) => (
            <Link
              key={doc.path}
              to={`/f/${doc.path}`}
              className={`flex items-center gap-2.5 truncate rounded-md px-2.5 py-1.5 text-sm ${
                location.pathname === `/f/${doc.path}` ? "bg-(--color-bg-hover) font-medium" : "text-(--color-text-muted) hover:bg-(--color-bg-hover) hover:text-(--color-text)"
              }`}
              title={doc.path}
            >
              <FolderClosed size={14} className="shrink-0 opacity-70" />
              <span className="truncate">{doc.title}</span>
            </Link>
          ))}
        </Section>
      )}
    </div>
  );
}

/** Whether ``pathname`` names a record reachable from this tree (its own
 * root's records, or any descendant directory's), so a project can start
 * expanded while its own page or one of its pages is open. */
function treeContainsPath(tree: TreeNode, pathname: string): boolean {
  if (tree.records.some((record) => `/r/${record.id}` === pathname)) return true;
  return tree.children.some((child) => treeContainsPath(child, pathname));
}

/** One project in the sidebar: a normal expandable node (chevron + link),
 * not a separate "Show pages" link buried under it. Starts expanded while
 * the current page is the project's own page or one of its pages, and
 * stays expanded once opened even after navigating elsewhere. */
function ProjectNode({ project }: { project: NavPayload["projects"][number] }) {
  const location = useLocation();
  const isActive = location.pathname === `/p/${project.id}` || treeContainsPath(project.tree, location.pathname);
  const [open, setOpen] = useState(isActive);
  useEffect(() => {
    if (isActive) setOpen(true);
  }, [isActive]);

  const hasContent = project.tree.records.length > 0 || project.tree.children.length > 0 || project.tree.broken.length > 0;

  return (
    <div>
      <div className="flex items-center">
        {hasContent ? (
          <button
            type="button"
            onClick={() => setOpen((value) => !value)}
            className="flex h-6 w-5 shrink-0 items-center justify-center text-(--color-text-faint)"
            aria-label={open ? "Collapse" : "Expand"}
          >
            <ChevronRight size={13} className={open ? "rotate-90 transition-transform" : "transition-transform"} />
          </button>
        ) : (
          <span className="w-5 shrink-0" />
        )}
        <Link
          to={`/p/${project.id}`}
          className={`flex min-w-0 flex-1 items-center gap-2 truncate rounded-md px-1 py-1 text-sm ${
            location.pathname === `/p/${project.id}` ? "bg-(--color-bg-hover) font-medium" : "hover:bg-(--color-bg-hover)"
          }`}
        >
          <FolderKanban size={14} className="shrink-0 opacity-70" />
          <span className="truncate">{project.title}</span>
        </Link>
      </div>
      {open && hasContent && (
        <div className="ml-5 border-l border-(--color-border) pl-1.5">
          {project.tree.records.map((record) => (
            <TreeNodeView
              key={record.id}
              node={{ name: record.title, overview: record, records: [], broken: [], children: [] }}
              depth={1}
            />
          ))}
          {project.tree.broken.map((entry) => (
            <div key={entry.path} className="truncate px-2 py-1 text-xs text-(--color-accent-red-text)" title={entry.message}>
              {entry.path.split("/").pop()}
            </div>
          ))}
          {project.tree.children.map((child) => (
            <TreeNodeView key={child.name} node={child} depth={1} />
          ))}
        </div>
      )}
    </div>
  );
}
