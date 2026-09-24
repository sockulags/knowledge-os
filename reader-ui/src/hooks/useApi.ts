import { useEffect, useRef, useState } from "react";
import { ApiNotFoundError, ApiUnreachableError } from "../api/client";

export interface ApiState<T> {
  data: T | null;
  loading: boolean;
  notFound: boolean;
  error: string | null;
  /** True when `error` is a network-level failure (the core was not
   * reachable at all) rather than a real response from it. A page shows
   * `networkErrorMessage(nav?.language)` instead of `error` in that case. */
  unreachable: boolean;
}

/** Fetch once per `key` change, tracking loading/not-found/error state so a
 * page can show a skeleton, a not-found page, or the loaded content without
 * duplicating that three-way branch everywhere. `key` is a plain dependency
 * array value (usually a route param) so navigating between two records
 * re-fetches instead of reusing stale state. */
export function useApi<T>(loader: () => Promise<T>, deps: unknown[]): ApiState<T> {
  const [state, setState] = useState<ApiState<T>>({ data: null, loading: true, notFound: false, error: null, unreachable: false });
  const loaderRef = useRef(loader);
  loaderRef.current = loader;

  useEffect(() => {
    let cancelled = false;
    setState({ data: null, loading: true, notFound: false, error: null, unreachable: false });
    loaderRef
      .current()
      .then((data) => {
        if (!cancelled) setState({ data, loading: false, notFound: false, error: null, unreachable: false });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiNotFoundError) {
          setState({ data: null, loading: false, notFound: true, error: null, unreachable: false });
        } else if (err instanceof ApiUnreachableError) {
          setState({ data: null, loading: false, notFound: false, error: err.message, unreachable: true });
        } else {
          const message = err instanceof Error ? err.message : "Something went wrong.";
          setState({ data: null, loading: false, notFound: false, error: message, unreachable: false });
        }
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return state;
}
