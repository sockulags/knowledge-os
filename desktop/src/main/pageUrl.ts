import { join } from 'path'
import { pathToFileURL } from 'url'

/** The shell's own pages, built by electron-vite into the renderer folder. */
export type ShellPage = 'index' | 'referat' | 'clone'

/**
 * The URL of a shell page: from the dev server when one runs (the start page
 * is its root URL as given), otherwise the built file in `rendererDir`.
 */
export function pageUrl(page: ShellPage, devServer: string | null, rendererDir: string): string {
  if (devServer !== null) {
    return page === 'index' ? devServer : `${devServer.replace(/\/+$/, '')}/${page}.html`
  }
  return pathToFileURL(join(rendererDir, `${page}.html`)).href
}
