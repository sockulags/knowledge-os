// The one place the interface keeps its own copy of user-facing copy, for
// the moment before the nav payload (which carries the server's copy, see
// `NavPayload.language`) has loaded, or when it never does because the core
// itself is unreachable. Keep this in sync with
// `knowledge_os/reader/strings.py`'s `NETWORK_UNREACHABLE_ERROR`.
export const NETWORK_ERROR_FALLBACK =
  "Knowledge OS couldn't reach its local service. If the app was just closed or restarted, reload the window.";

/** The friendly message for a request that never reached the core at all,
 * preferring the server's own copy (from the nav payload) when it is
 * available and falling back to the built-in copy above otherwise. */
export function networkErrorMessage(language: { network_error?: string } | null | undefined): string {
  return language?.network_error ?? NETWORK_ERROR_FALLBACK;
}

/** What a page shows in place of its content after a failed `useApi` load:
 * the friendly network message when the core was unreachable, the load
 * error's own message otherwise (falling back to the nav payload's generic
 * `load_error`, then to `fallback`). Never the browser's own raw fetch
 * error. */
export function loadErrorMessage(
  state: { error: string | null; unreachable: boolean },
  language: { load_error?: string; network_error?: string } | null | undefined,
  fallback: string,
): string {
  if (state.unreachable) return networkErrorMessage(language);
  return state.error ?? language?.load_error ?? fallback;
}
