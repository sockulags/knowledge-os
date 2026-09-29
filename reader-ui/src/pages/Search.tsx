import { useEffect, useRef, useState, type FormEvent } from "react";
import { useSearchParams, Link } from "react-router";
import { Search as SearchIcon, Sparkles } from "lucide-react";
import { api, ApiUnreachableError } from "../api/client";
import type { SearchPayload, SemanticStatus } from "../api/types";
import { semanticSearch } from "../api/write";
import { Callout, LoadError } from "../components/Callout";
import { PageSkeleton } from "../components/Skeleton";
import { useShell } from "../components/Shell";
import { networkErrorMessage } from "../lib/language";
import { useDocumentTitle } from "../hooks/useDocumentTitle";

const FILTER_KEYS = ["type", "status", "scope", "record_kind", "trust"] as const;

export function Search() {
  const { nav } = useShell();
  useDocumentTitle(nav?.workspace_name, "Search");
  const [params, setParams] = useSearchParams();
  const [data, setData] = useState<SearchPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [inputValue, setInputValue] = useState(params.get("q") ?? "");
  // Bumped when search by meaning becomes ready, to run the search again.
  const [semanticRound, setSemanticRound] = useState(0);

  useEffect(() => {
    setInputValue(params.get("q") ?? "");
  }, [params]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api
      .search(`?${params.toString()}`)
      .then((result) => {
        // A faster response to an older query string must never overwrite
        // a slower response to the current one (e.g. typing quickly, or
        // toggling a filter before the previous request lands).
        if (!cancelled) {
          setData(result);
          setError(null);
        }
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof ApiUnreachableError ? networkErrorMessage(nav?.language) : "Could not search the workspace.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [params, nav, semanticRound]);

  function updateFilter(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  }

  function submitQuery(event: FormEvent) {
    event.preventDefault();
    const next = new URLSearchParams(params);
    if (inputValue.trim()) next.set("q", inputValue.trim());
    else next.delete("q");
    setParams(next);
  }

  return (
    <div className="mx-auto w-full max-w-[760px] px-6 py-12 sm:px-10">
      <h1 className="kos-title">Search</h1>

      <form onSubmit={submitQuery} className="kos-input mt-6 flex items-center gap-2.5 rounded-(--radius-card) px-3.5 py-2.5">
        <SearchIcon size={17} className="shrink-0 text-(--color-accent-text)" />
        <input
          value={inputValue}
          onChange={(event) => setInputValue(event.target.value)}
          placeholder="Search the workspace"
          className="w-full bg-transparent text-base outline-none placeholder:text-(--color-text-faint) focus-visible:outline-none"
        />
      </form>

      {data && data.search_available && data.semantic && (
        <SemanticNote initial={data.semantic} onReady={() => setSemanticRound((round) => round + 1)} />
      )}

      {data && data.search_available && (
        <div className="mt-4 flex flex-wrap gap-2">
          {FILTER_KEYS.map((key) => {
            const options = data.filter_options[key] ?? [];
            const label = data.filter_labels[key] ?? key;
            return (
              <select
                key={key}
                value={params.get(key) ?? ""}
                onChange={(event) => updateFilter(key, event.target.value)}
                className="kos-input py-1.5 text-[13px] text-(--color-text-muted)"
              >
                <option value="">{label}: Any</option>
                {options.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            );
          })}
        </div>
      )}

      <div className="mt-8">
        {loading && <PageSkeleton />}
        {!loading && error && <LoadError>{error}</LoadError>}
        {!loading && !error && data && !data.search_available && (
          <Callout tone="neutral">
            <p>{data.disabled_reason}</p>
            <code className="kos-code mt-1 inline-block">
              kos index
            </code>
          </Callout>
        )}
        {!loading && !error && data && data.search_available && (
          <>
            {params.get("q") && (
              <p className="mb-3 text-sm text-(--color-text-faint)">{data.result_count_label}</p>
            )}
            <div className="space-y-1">
              {data.results.map((result) => (
                <Link
                  key={result.id}
                  to={`/r/${result.id}`}
                  className="block rounded-(--radius-card) border border-transparent px-3.5 py-3 transition-colors hover:border-(--color-border) hover:bg-(--color-bg-raised)"
                >
                  <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                    <span className="font-medium">{result.title}</span>
                    <span className="flex items-center gap-2 text-xs text-(--color-text-faint)">
                      {result.match_label && (
                        <span
                          className="inline-flex items-center gap-1 rounded-full border border-(--color-border) px-1.5 py-px"
                          title={data.semantic?.match_hint}
                        >
                          <Sparkles size={11} />
                          {result.match_label}
                        </span>
                      )}
                      <span>
                        {result.type_label}
                        {result.project ? ` · ${result.project}` : ""}
                      </span>
                    </span>
                  </div>
                  <p
                    className="mt-1 truncate text-sm text-(--color-text-muted) [&_mark]:rounded-[3px] [&_mark]:bg-(--color-accent-yellow-bg) [&_mark]:px-0.5 [&_mark]:text-(--color-text) [&_mark]:not-italic"
                    dangerouslySetInnerHTML={{ __html: result.snippet_html }}
                  />
                </Link>
              ))}
              {params.get("q") && data.results.length === 0 && (
                <p className="py-8 text-center text-sm text-(--color-text-faint)">No matching records.</p>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

/** Where search by meaning stands, under the search field: an offer to
 * download the model, its progress, or a quiet line once it works. A stale
 * index is refreshed in the background (serving a search never writes, so
 * the page asks for it). `onReady` runs the search again once meaning
 * results are available. */
function SemanticNote({ initial, onReady }: { initial: SemanticStatus; onReady: () => void }) {
  const [status, setStatus] = useState(initial);
  const [starting, setStarting] = useState(false);
  const asked = useRef(false);
  const wasReady = useRef(initial.state === "ready");

  useEffect(() => {
    setStatus(initial);
  }, [initial]);

  useEffect(() => {
    if (initial.state === "stale" && !asked.current) {
      asked.current = true;
      void semanticSearch.refresh().then((outcome) => {
        if (outcome.ok) setStatus(outcome.data);
      });
    }
  }, [initial.state]);

  const busy = ["installing", "loading", "indexing", "stale"].includes(status.state);
  useEffect(() => {
    if (!busy) return;
    const timer = window.setInterval(() => {
      api
        .semantic()
        .then((next) => {
          setStatus(next);
          if (next.state === "ready" && !wasReady.current) {
            wasReady.current = true;
            onReady();
          }
        })
        .catch(() => undefined);
    }, 1500);
    return () => window.clearInterval(timer);
  }, [busy, onReady]);

  if (status.state === "unavailable" || (status.state === "ready" && !status.message)) return null;

  async function install() {
    setStarting(true);
    const outcome = await semanticSearch.install();
    setStarting(false);
    if (outcome.ok) setStatus(outcome.data);
  }

  const percent = status.total_bytes > 0 ? Math.min(100, Math.floor((status.done_bytes * 100) / status.total_bytes)) : 0;
  return (
    <div className="mt-3 flex items-start gap-2.5 text-[13px] text-(--color-text-faint)" aria-live="polite">
      <Sparkles size={14} className="mt-0.5 shrink-0" />
      <div className="space-y-2">
        <p>
          {status.message}
          {status.state === "installing" ? ` ${percent}%` : ""}
        </p>
        {status.state === "off" && (
          <button type="button" className="kos-btn kos-btn-secondary kos-btn-sm text-xs" disabled={starting} onClick={() => void install()}>
            {status.install_label}
          </button>
        )}
        {status.error && (status.state === "off" || status.state === "failed") && <p className="text-(--color-accent-red-text)">{status.error}</p>}
      </div>
    </div>
  );
}
