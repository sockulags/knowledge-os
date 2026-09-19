import { useEffect, useRef, useState } from "react";
import { ApiNotFoundError } from "../api/client";

export interface ApiState<T> {
  data: T | null;
  loading: boolean;
  notFound: boolean;
  error: string | null;
}

/** Fetch once per `key` change, tracking loading/not-found/error state so a
 * page can show a skeleton, a not-found page, or the loaded content without
 * duplicating that three-way branch everywhere. `key` is a plain dependency
 * array value (usually a route param) so navigating between two records
 * re-fetches instead of reusing stale state. */
export function useApi<T>(loader: () => Promise<T>, deps: unknown[]): ApiState<T> {
  const [state, setState] = useState<ApiState<T>>({ data: null, loading: true, notFound: false, error: null });
  const loaderRef = useRef(loader);
  loaderRef.current = loader;

  useEffect(() => {
    let cancelled = false;
    setState({ data: null, loading: true, notFound: false, error: null });
    loaderRef
      .current()
      .then((data) => {
        if (!cancelled) setState({ data, loading: false, notFound: false, error: null });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiNotFoundError) {
          setState({ data: null, loading: false, notFound: true, error: null });
        } else {
          const message = err instanceof Error ? err.message : "Something went wrong.";
          setState({ data: null, loading: false, notFound: false, error: message });
        }
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return state;
}
