import { useState, type ReactNode } from "react";
import { Link, useLocation } from "react-router";
import { ChevronRight, Home, LayoutGrid, Search, FolderKanban, BookOpen, FolderClosed } from "lucide-react";
import type { NavPayload } from "../api/types";
import { TreeNodeView } from "./ProjectTree";

function NavRow({ to, icon, label, active }: { to: string; icon: ReactNode; label: string; active: boolean }) {
  return (
    <Link
      to={to}
      className={`flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-sm ${
        active ? "bg-(--color-bg-hover) font-medium" : "text-(--color-text-muted) hover:bg-(--color-bg-hover) hover:text-(--color-text)"
      }`}
    >
      {icon}
      {label}
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
          Ctrl K
        </kbd>
      </button>

      <nav className="space-y-0.5">
        <NavRow to="/" icon={<Home size={15} />} label="Home" active={location.pathname === "/"} />
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
          nav.projects.map((project) => (
            <div key={project.id}>
              <div className="flex items-center">
                <TreeToggle />
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
              <ProjectSubtree tree={project.tree} />
            </div>
          ))
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

function TreeToggle() {
  return <span className="w-5 shrink-0" />;
}

function ProjectSubtree({ tree }: { tree: NavPayload["projects"][number]["tree"] }) {
  const [open, setOpen] = useState(false);
  const hasContent = tree.records.length > 0 || tree.children.length > 0 || tree.broken.length > 0;
  if (!hasContent) return null;
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="ml-5 flex items-center gap-1 px-1 py-0.5 text-xs text-(--color-text-faint) hover:text-(--color-text-muted)"
      >
        <ChevronRight size={11} className={open ? "rotate-90 transition-transform" : "transition-transform"} />
        {open ? "Hide pages" : "Show pages"}
      </button>
      {open && (
        <div className="ml-5 border-l border-(--color-border) pl-1.5">
          {tree.records.map((record) => (
            <TreeNodeView key={record.id} node={{ name: record.title, overview: record, records: [], broken: [], children: [] }} depth={1} />
          ))}
          {tree.children.map((child) => (
            <TreeNodeView key={child.name} node={child} depth={1} />
          ))}
        </div>
      )}
    </div>
  );
}
