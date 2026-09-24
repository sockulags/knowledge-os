import { useEffect, useState, type FormEvent } from "react";
import { useSearchParams, Link } from "react-router";
import { Search as SearchIcon } from "lucide-react";
import { api } from "../api/client";
import type { SearchPayload } from "../api/types";
import { Callout } from "../components/Callout";
import { PageSkeleton } from "../components/Skeleton";

const FILTER_KEYS = ["type", "status", "scope", "record_kind", "trust"] as const;

export function Search() {
  const [params, setParams] = useSearchParams();
  const [data, setData] = useState<SearchPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [inputValue, setInputValue] = useState(params.get("q") ?? "");

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
        if (!cancelled) setData(result);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [params]);

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
        {!loading && data && !data.search_available && (
          <Callout tone="neutral">
            <p>{data.disabled_reason}</p>
            <code className="kos-code mt-1 inline-block">
              kos index
            </code>
          </Callout>
        )}
        {!loading && data && data.search_available && (
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
                    <span className="text-xs text-(--color-text-faint)">
                      {result.type_label}
                      {result.project ? ` · ${result.project}` : ""}
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
