import { useState, type ReactNode } from "react";
import { Link, useLocation } from "react-router";
import { ChevronRight, Home, Inbox, LayoutGrid, Search, BookOpen, FolderClosed, Plus } from "lucide-react";
import type { NavPayload } from "../api/types";
import { SidebarProject } from "./ProjectTree";
import { useStructure } from "./Structure";
import { SHORTCUT_KEYS } from "../lib/quickSwitch";
import mark from "../assets/mark.svg";

const rowActive = "bg-(--color-bg-active) font-medium text-(--color-text) [&>svg]:text-(--color-accent-text) [&>svg]:opacity-100";
const rowIdle = "text-(--color-text-muted) hover:bg-(--color-bg-hover) hover:text-(--color-text)";

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
      className={`flex items-center gap-2.5 rounded-(--radius-control) px-2.5 py-1.5 text-sm transition-colors ${active ? rowActive : rowIdle}`}
    >
      {icon}
      <span className="flex-1">{label}</span>
      {count !== undefined && count > 0 && (
        <span
          className="min-w-5 rounded-[5px] bg-(--color-accent-amber-bg) px-1.5 py-[3px] text-center text-xs font-semibold leading-none text-(--color-accent-amber-text) tabular-nums"
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
  action,
  children,
}: {
  title: string;
  defaultOpen?: boolean;
  /** A small button at the right of the section heading. */
  action?: ReactNode;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="mt-5">
      <div className="mb-1 flex items-center">
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          aria-expanded={open}
          className="kos-eyebrow flex flex-1 items-center gap-1 rounded-(--radius-control) px-1 hover:text-(--color-text-muted)"
        >
          <ChevronRight size={11} className={open ? "rotate-90 transition-transform" : "transition-transform"} />
          {title}
        </button>
        {action}
      </div>
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
  const structure = useStructure();

  return (
    <div className="flex h-full flex-col overflow-y-auto px-3 py-4" onClick={onNavigate}>
      <Link to="/" className="mb-4 flex min-w-0 items-center gap-2.5 rounded-(--radius-control) px-1.5 py-1">
        <img src={mark} alt="" className="h-[22px] w-[22px] shrink-0" />
        <span className="truncate font-serif text-[16px] font-semibold tracking-[-0.005em]">
          {nav?.workspace_name ?? "Knowledge OS"}
        </span>
      </Link>

      <button
        type="button"
        onClick={(event) => {
          event.stopPropagation();
          onOpenQuickFind();
        }}
        className="mb-3 flex items-center justify-between rounded-(--radius-control) border border-(--color-border-strong) bg-(--color-bg-raised) px-2.5 py-1.5 text-sm text-(--color-text-faint) transition-colors hover:border-(--color-text-faint) hover:text-(--color-text-muted)"
      >
        <span className="flex items-center gap-2">
          <Search size={14} />
          Search
        </span>
        <kbd className="kos-kbd">
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

      <Section
        title="Projects"
        action={
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              structure.newProject();
            }}
            className="flex h-6 w-6 items-center justify-center rounded-[5px] text-(--color-text-faint) transition-colors hover:bg-(--color-bg-hover) hover:text-(--color-text)"
            aria-label="New project"
            title="New project"
          >
            <Plus size={13} />
          </button>
        }
      >
        {nav?.projects.length ? (
          nav.projects.map((project) => <SidebarProject key={project.id} project={project} />)
        ) : (
          <p className="px-2 py-1 text-sm text-(--color-text-faint)">No project yet.</p>
        )}
      </Section>

      {nav && nav.skills.length > 0 && (
        <Section title="Skills" defaultOpen={false}>
          {nav.skills.map((skill) => (
            <Link
              key={skill.name}
              to={`/s/${skill.name}`}
              className={`flex items-center gap-2.5 truncate rounded-(--radius-control) px-2.5 py-1.5 text-sm ${
                location.pathname === `/s/${skill.name}` ? rowActive : rowIdle
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
              className={`flex items-center gap-2.5 truncate rounded-(--radius-control) px-2.5 py-1.5 text-sm ${
                location.pathname === `/f/${doc.path}` ? rowActive : rowIdle
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
