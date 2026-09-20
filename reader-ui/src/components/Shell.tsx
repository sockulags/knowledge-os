import { useEffect, useState } from "react";
import { Outlet } from "react-router";
import { Menu, PanelLeftClose, PanelLeft } from "lucide-react";
import { api } from "../api/client";
import type { NavPayload } from "../api/types";
import { Sidebar } from "./Sidebar";
import { QuickFind } from "./QuickFind";
import { ThemeToggle } from "./ThemeToggle";
import { ScrollToTop } from "./ScrollToTop";

/** The app shell: a ~260px left sidebar on a tinted ground, a centred
 * reading column, and the Ctrl K command palette. Collapses to a slide-over
 * drawer below 768px (design brief). */
export function Shell() {
  const [nav, setNav] = useState<NavPayload | null>(null);
  const [collapsed, setCollapsed] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [quickFindOpen, setQuickFindOpen] = useState(false);

  useEffect(() => {
    api.nav().then(setNav).catch(() => setNav(null));
  }, []);

  useEffect(() => {
    function handleKey(event: KeyboardEvent) {
      const isShortcut = (event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k";
      if (isShortcut) {
        event.preventDefault();
        setQuickFindOpen(true);
      }
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, []);

  return (
    <div className="flex min-h-screen">
      <ScrollToTop />
      {/* Desktop sidebar: sticky and self-start so it stays pinned to the
          viewport with its own scroll, rather than stretching to the main
          column's full height (the flex row's default cross-axis stretch)
          and scrolling away with the page on anything taller than one
          screen. */}
      <aside
        className={`sticky top-0 hidden h-screen shrink-0 self-start border-r border-(--color-border) bg-(--color-bg-sidebar) md:block ${
          collapsed ? "w-0 overflow-hidden border-r-0" : "w-64"
        } transition-[width] duration-150`}
      >
        <div className="h-full w-64">
          <Sidebar nav={nav} onOpenQuickFind={() => setQuickFindOpen(true)} />
        </div>
      </aside>

      {/* Mobile drawer */}
      {drawerOpen && (
        <div className="fixed inset-0 z-40 md:hidden">
          <div className="absolute inset-0 bg-black/30" onClick={() => setDrawerOpen(false)} />
          <aside className="absolute inset-y-0 left-0 w-72 border-r border-(--color-border) bg-(--color-bg-sidebar)">
            <Sidebar
              nav={nav}
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
        <header className="sticky top-0 z-30 flex items-center justify-between border-b border-(--color-border) bg-(--color-bg) px-3 py-2">
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => setDrawerOpen(true)}
              className="flex h-8 w-8 items-center justify-center rounded-md text-(--color-text-muted) hover:bg-(--color-bg-hover) md:hidden"
              aria-label="Open navigation"
            >
              <Menu size={17} />
            </button>
            <button
              type="button"
              onClick={() => setCollapsed((value) => !value)}
              className="hidden h-8 w-8 items-center justify-center rounded-md text-(--color-text-muted) hover:bg-(--color-bg-hover) md:flex"
              aria-label={collapsed ? "Show sidebar" : "Hide sidebar"}
            >
              {collapsed ? <PanelLeft size={16} /> : <PanelLeftClose size={16} />}
            </button>
          </div>
          <ThemeToggle />
        </header>
        <main>
          <Outlet />
        </main>
      </div>

      <QuickFind open={quickFindOpen} onClose={() => setQuickFindOpen(false)} nav={nav} />
    </div>
  );
}
