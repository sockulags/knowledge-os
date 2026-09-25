import { useCallback, useEffect, useMemo, useState } from "react";
import { Outlet, useLocation, useOutletContext } from "react-router";
import { Menu, PanelLeftClose, PanelLeft } from "lucide-react";
import { api } from "../api/client";
import type { NavPayload } from "../api/types";
import { Sidebar } from "./Sidebar";
import { SidebarResizer } from "./SidebarResizer";
import { QuickFind } from "./QuickFind";
import { ThemeToggle } from "./ThemeToggle";
import { ScrollToTop } from "./ScrollToTop";
import { SyncBar, SyncFailureBanner } from "./SyncBar";
import { StructureProvider } from "./Structure";
import { UndoNotices } from "./UndoNotices";
import { useSync, type SyncState } from "../hooks/useSync";
import { MAC, isQuickSwitchShortcut } from "../lib/quickSwitch";
import { showsOutcome } from "../lib/pendingActions";
import { pendingActions, useOnPendingSettled, usePendingEntries } from "../lib/pendingStore";
import { prepareSession } from "../api/write";

export interface ShellContext {
  /** Reload the sidebar after a write changed titles or added a page. */
  refreshNav: () => void;
  /** Git status for the status line and the sync page. */
  sync: SyncState;
  /** The shell's own nav payload (sidebar tree, quick-find index, and the
   * shared `language` copy pages read shell-wide fallback text from), or
   * null before the first load resolves. */
  nav: NavPayload | null;
}

export function useShell(): ShellContext {
  return useOutletContext<ShellContext>();
}

/** The app shell: a resizable left sidebar (256px by default) on a tinted ground, a centred
 * reading column, and the Ctrl K command palette. Collapses to a slide-over
 * drawer below 768px (design brief). */
export function Shell() {
  const [nav, setNav] = useState<NavPayload | null>(null);
  const [collapsed, setCollapsed] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [quickFindOpen, setQuickFindOpen] = useState(false);

  // Bumped after a sync pulls changes, which remounts the page so it
  // re-reads what the pull changed.
  const [dataVersion, setDataVersion] = useState(0);

  // When the nav request started, so a decision action that finished before
  // it no longer needs subtracting from the Decide count.
  const [navLoadedAt, setNavLoadedAt] = useState(0);

  const loadNav = useCallback(() => {
    const started = Date.now();
    api
      .nav()
      .then((payload) => {
        setNav(payload);
        setNavLoadedAt(started);
      })
      .catch(() => setNav(null));
  }, []);

  const sync = useSync(
    useCallback(() => {
      loadNav();
      setDataVersion((value) => value + 1);
    }, [loadNav]),
  );
  const refreshNav = loadNav;

  useEffect(() => {
    loadNav();
  }, [loadNav]);

  // One-click decision actions wait a few seconds for Undo before they are
  // written (lib/pendingActions.ts). Leaving never drops one: a new route
  // sends everything still waiting and then reloads the page it shows, and a
  // page that is hidden or closed sends it with keepalive.
  const location = useLocation();
  useEffect(() => {
    if (pendingActions.pendingCount() === 0) return;
    void pendingActions.flushAll().then((sent) => {
      if (sent > 0) setDataVersion((value) => value + 1);
    });
  }, [location.pathname]);
  useEffect(() => {
    prepareSession();
    const flush = () => void pendingActions.flushAll({ keepalive: true });
    window.addEventListener("pagehide", flush);
    return () => window.removeEventListener("pagehide", flush);
  }, []);
  useOnPendingSettled(loadNav);

  // The sidebar's Decide count leaves out proposals already accepted or
  // withdrawn here, from the click on.
  const pending = usePendingEntries();
  const acted = pending.filter((entry) => showsOutcome(entry, navLoadedAt)).length;
  const shownNav = useMemo(
    () =>
      nav !== null && acted > 0
        ? { ...nav, decide: { ...nav.decide, count: Math.max(nav.decide.count - acted, 0) } }
        : nav,
    [nav, acted],
  );

  useEffect(() => {
    function handleKey(event: KeyboardEvent) {
      // On the window, so it works from every view, the editor included.
      if (isQuickSwitchShortcut(event, MAC)) {
        event.preventDefault();
        setQuickFindOpen(true);
      }
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, []);

  // After a structure change: reload the sidebar, and the page too unless
  // it holds unsaved edits (the provider decides).
  const structureChanged = useCallback(
    (reloadPage: boolean) => {
      loadNav();
      if (reloadPage) setDataVersion((value) => value + 1);
    },
    [loadNav],
  );

  return (
    <StructureProvider nav={nav} onChanged={structureChanged}>
    <div className="flex min-h-screen">
      <ScrollToTop />
      {/* Desktop sidebar: sticky and self-start so it stays pinned to the
          viewport with its own scroll, rather than stretching to the main
          column's full height (the flex row's default cross-axis stretch)
          and scrolling away with the page on anything taller than one
          screen. */}
      <aside
        className={`kos-sidebar sticky top-0 z-20 hidden h-screen shrink-0 self-start border-r border-(--color-border) bg-(--color-bg-sidebar) md:block ${
          collapsed ? "w-0 overflow-hidden border-r-0" : ""
        }`}
      >
        <div className="kos-sidebar-inner h-full">
          <Sidebar nav={shownNav} onOpenQuickFind={() => setQuickFindOpen(true)} />
        </div>
        {!collapsed && (
          <SidebarResizer label={nav?.language.sidebar_resize_label} hint={nav?.language.sidebar_resize_hint} />
        )}
      </aside>

      {/* Mobile drawer */}
      {drawerOpen && (
        <div className="fixed inset-0 z-40 md:hidden">
          <div className="kos-scrim absolute inset-0" onClick={() => setDrawerOpen(false)} />
          <aside className="absolute inset-y-0 left-0 w-72 border-r border-(--color-border) bg-(--color-bg-sidebar)">
            <Sidebar
              nav={shownNav}
              onNavigate={() => setDrawerOpen(false)}
              onOpenQuickFind={() => {
                setDrawerOpen(false);
                setQuickFindOpen(true);
              }}
            />
          </aside>
        </div>
      )}

      <div className="min-w-0 flex-1">
        <header className="sticky top-0 z-30 flex items-center justify-between border-b border-(--color-border) bg-[color-mix(in_srgb,var(--color-bg)_92%,transparent)] px-3 py-2 backdrop-blur-sm">
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => setDrawerOpen(true)}
              className="kos-icon-btn md:hidden"
              aria-label="Open navigation"
            >
              <Menu size={17} />
            </button>
            <button
              type="button"
              onClick={() => setCollapsed((value) => !value)}
              className="kos-icon-btn hidden md:inline-flex"
              aria-label={collapsed ? "Show sidebar" : "Hide sidebar"}
            >
              {collapsed ? <PanelLeft size={16} /> : <PanelLeftClose size={16} />}
            </button>
          </div>
          <div className="flex min-w-0 items-center gap-2">
            <SyncBar sync={sync} />
            <ThemeToggle />
          </div>
        </header>
        <SyncFailureBanner sync={sync} />
        <main key={dataVersion}>
          <Outlet context={{ refreshNav, sync, nav } satisfies ShellContext} />
        </main>
      </div>

      <QuickFind open={quickFindOpen} onClose={() => setQuickFindOpen(false)} nav={nav} />
      <UndoNotices />
    </div>
    </StructureProvider>
  );
}
