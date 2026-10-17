import { useCallback, useEffect, useRef, useState } from "react";
import { ApiNotFoundError, ApiUnreachableError } from "../api/client";

export interface ApiState<T> {
  data: T | null;
  loading: boolean;
  notFound: boolean;
  /** The failed load's message, also set for a not-found answer (pages
   * check `notFound` first). */
  error: string | null;
  /** True when `error` is a network-level failure (the core was not
   * reachable at all) rather than a real response from it. A page shows
   * `loadErrorMessage(state, nav?.language, ...)` instead of `error`, so the
   * nav payload is read at render time and never needs to be a dependency. */
  unreachable: boolean;
}

export interface ApiOptions {
  /** Keep the last loaded `data` while a new request runs and after it
   * fails, instead of dropping back to nothing. For pages that reload in
   * place (a table under its filters, an inbox after an action). */
  keepData?: boolean;
}

export interface ReloadOptions {
  /** Ask again without showing it: `loading` stays false and a failure
   * leaves the current state as it was. For background polling. */
  quiet?: boolean;
}

export interface ApiHandle<T> extends ApiState<T> {
  /** Run the loader again with the same dependencies. Stable across renders. */
  reload: (options?: ReloadOptions) => void;
}

const INITIAL = { data: null, loading: true, notFound: false, error: null, unreachable: false };

/** Fetch once per `deps` change, tracking loading/not-found/error state so a
 * page can show a skeleton, a not-found page, or the loaded content without
 * duplicating that three-way branch everywhere. `deps` is a plain dependency
 * array (usually a route param) so navigating between two records re-fetches
 * instead of reusing stale state. Only the newest request may write the
 * state: a slower answer to an older request is dropped. */
export function useApi<T>(loader: () => Promise<T>, deps: unknown[], options: ApiOptions = {}): ApiHandle<T> {
  const keepData = options.keepData ?? false;
  const [state, setState] = useState<ApiState<T>>(INITIAL);
  const loaderRef = useRef(loader);
  loaderRef.current = loader;
  const latest = useRef(0);

  const run = useCallback(
    (quiet: boolean) => {
      const request = ++latest.current;
      if (!quiet) setState((previous) => (keepData ? { ...previous, loading: true } : INITIAL));
      loaderRef
        .current()
        .then((data) => {
          if (request === latest.current) setState({ data, loading: false, notFound: false, error: null, unreachable: false });
        })
        .catch((err: unknown) => {
          if (request !== latest.current || quiet) return;
          setState((previous) => {
            const data = keepData ? previous.data : null;
            if (err instanceof ApiNotFoundError) return { data, loading: false, notFound: true, error: err.message, unreachable: false };
            const message = err instanceof Error ? err.message : "Something went wrong.";
            return { data, loading: false, notFound: false, error: message, unreachable: err instanceof ApiUnreachableError };
          });
        });
    },
    [keepData],
  );

  useEffect(() => {
    run(false);
    return () => {
      // Drop whatever is still in flight once the dependencies change or
      // the page unmounts.
      latest.current++;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  const reload = useCallback((reloadOptions?: ReloadOptions) => run(reloadOptions?.quiet ?? false), [run]);

  return { ...state, reload };
}
