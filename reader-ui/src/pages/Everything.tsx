import { useEffect, useState } from "react";
import { useSearchParams, Link } from "react-router";
import { ArrowUp, ArrowDown, ArrowUpDown } from "lucide-react";
import { api } from "../api/client";
import { PageSkeleton } from "../components/Skeleton";
import { LoadError, BrokenRecordCallout } from "../components/Callout";
import { Pill } from "../components/Pill";
import type { EverythingPayload } from "../api/types";

const FILTER_KEYS = ["type", "status", "record_kind", "trust", "scope"] as const;

const SORT_COLUMNS: { key: string; label: string }[] = [
  { key: "title", label: "Title" },
  { key: "type", label: "Kind" },
  { key: "updated", label: "Updated" },
  { key: "project", label: "Project" },
];

export function Everything() {
  const [params, setParams] = useSearchParams();
  const [data, setData] = useState<EverythingPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api
      .everything(`?${params.toString()}`)
      .then((result) => {
        // A faster response to an older filter/sort combination must never
        // overwrite a slower response to the current one (mirrors Search).
        if (!cancelled) {
          setData(result);
          setError(null);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Something went wrong.");
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

  function toggleSort(column: string) {
    const next = new URLSearchParams(params);
    const currentSort = params.get("sort") || "title";
    const currentDir = params.get("dir") || "asc";
    if (currentSort === column) {
      next.set("dir", currentDir === "asc" ? "desc" : "asc");
    } else {
      next.set("sort", column);
      next.set("dir", "asc");
    }
    setParams(next, { replace: true });
  }

  if (loading && !data) return <PageSkeleton />;
  if (error || !data) return <LoadError>{error ?? "Could not load the catalog."}</LoadError>;

  const sortKey = data.sort;

  return (
    <div className="mx-auto w-full max-w-[1100px] px-6 py-12 sm:px-10">
      <h1 className="kos-title">{data.title}</h1>
      <p className="kos-lede">{data.intro}</p>

      <div className="mt-5 flex flex-wrap gap-2">
        {FILTER_KEYS.map((key) => {
          const options = data.filter_options[key] ?? [];
          const label = data.filter_labels[key] ?? key;
          if (options.length === 0) return null;
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

      <div className="kos-card mt-6 overflow-x-auto">
        <table className="w-full min-w-[720px] border-collapse text-sm">
          <thead>
            <tr className="border-b border-(--color-border) bg-(--color-bg-sidebar) text-left text-[13px] text-(--color-text-muted)">
              {SORT_COLUMNS.map((column) => {
                const active = sortKey === column.key;
                // An active column shows which way it's sorted (ArrowUp for
                // ascending, ArrowDown for descending) instead of the same
                // neutral glyph regardless of direction -- direction was
                // only readable before by clicking and comparing row order.
                const Icon = active ? (data.dir === "desc" ? ArrowDown : ArrowUp) : ArrowUpDown;
                return (
                  <th key={column.key} className="px-3 py-2 font-medium">
                    <button
                      type="button"
                      onClick={() => toggleSort(column.key)}
                      className={`-mx-1 flex items-center gap-1 rounded-(--radius-control) px-1 hover:text-(--color-text) ${active ? "text-(--color-text)" : ""}`}
                    >
                      {column.label}
                      <Icon size={12} className={active ? "opacity-100" : "opacity-30"} />
                    </button>
                  </th>
                );
              })}
              <th className="px-3 py-2 font-medium">Status</th>
              <th className="px-3 py-2 font-medium">Trust</th>
            </tr>
          </thead>
          <tbody>
            {data.entries.map((entry) => (
              <tr key={entry.id} className="border-b border-(--color-border) transition-colors last:border-0 hover:bg-(--color-bg-hover)">
                <td className="px-3 py-2">
                  <Link to={`/r/${entry.id}`} className="rounded-sm font-medium hover:underline hover:underline-offset-[3px]">
                    {entry.title}
                  </Link>
                </td>
                <td className="px-3 py-2 text-(--color-text-muted)">{entry.type_label}</td>
                <td className="whitespace-nowrap px-3 py-2 text-(--color-text-muted)" title={entry.updated}>
                  {entry.updated_display ?? entry.updated}
                </td>
                <td className="px-3 py-2 text-(--color-text-muted)">{entry.project_title ?? "—"}</td>
                <td className="px-3 py-2">
                  <Pill pill={entry.status_pill} />
                </td>
                <td className="px-3 py-2 text-(--color-text-muted)">{entry.trust_phrase ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {data.entries.length === 0 && (
          <p className="py-8 text-center text-sm text-(--color-text-faint)">No matching records.</p>
        )}
      </div>

      {data.skills.length > 0 && (
        <section className="mt-10">
          <h2 className="kos-eyebrow mb-2.5">Skills</h2>
          <div className="space-y-1">
            {data.skills.map((skill) => (
              <Link key={skill.name} to={`/s/${skill.name}`} className="kos-row px-2 py-1.5 text-sm">
                {skill.name}
              </Link>
            ))}
          </div>
        </section>
      )}

      {data.broken.length > 0 && (
        <section className="mt-10">
          <h2 className="kos-eyebrow mb-2.5">
            Could not be read
          </h2>
          {data.broken.map((entry) => (
            <BrokenRecordCallout key={entry.path} path={entry.path} message={entry.message} />
          ))}
        </section>
      )}
    </div>
  );
}
