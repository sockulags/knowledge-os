import { useEffect } from "react";

const APP_NAME = "Knowledge OS";

/** The one place `document.title` is written. The desktop shell does not
 * set its own window title once the reader has loaded (see the
 * `page-title-updated` handling in `desktop/src/main/index.ts`) --
 * Electron mirrors a BrowserWindow's title from its page's `document.title`
 * by default, so writing it here is enough to keep the OS window title and
 * the page in agreement, in the desktop app and in a plain browser alike.
 * The desktop app's own title bar shows the same page and workspace names,
 * read from `document.title`.
 *
 * Same format everywhere: "<page title> — <workspace> — Knowledge OS", or
 * "<workspace> — Knowledge OS" with no page title (home), falling back to
 * "Knowledge OS" alone before the workspace name has loaded. */
export function useDocumentTitle(workspaceName: string | null | undefined, pageTitle?: string | null): void {
  useEffect(() => {
    const parts = [pageTitle, workspaceName, APP_NAME].filter(
      (part): part is string => typeof part === "string" && part.trim().length > 0,
    );
    document.title = parts.length > 0 ? parts.join(" — ") : APP_NAME;
  }, [workspaceName, pageTitle]);
}
