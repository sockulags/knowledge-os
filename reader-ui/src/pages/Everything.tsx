import { useEffect, useState } from "react";
import { useSearchParams, Link } from "react-router";
import { ArrowUp, ArrowDown, ArrowUpDown } from "lucide-react";
import { api } from "../api/client";
import { PageSkeleton } from "../components/Skeleton";
import { Callout, BrokenRecordCallout } from "../components/Callout";
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
  if (error || !data) return <Callout tone="danger">{error ?? "Could not load the catalog."}</Callout>;

  const sortKey = data.sort;

  return (
    <div className="mx-auto w-full max-w-[1100px] px-6 py-12 sm:px-10">
      <h1 className="text-[26px] sm:text-[32px] font-semibold leading-tight tracking-tight">Everything</h1>
      <p className="mt-1.5 text-(--color-text-muted)">
        Every record, source, and discovery the workspace holds, in one flat list.
      </p>

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
              className="rounded-md border border-(--color-border) bg-(--color-bg) px-2.5 py-1.5 text-sm text-(--color-text-muted)"
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

      <div className="mt-6 overflow-x-auto rounded-lg border border-(--color-border)">
        <table className="w-full min-w-[720px] border-collapse text-sm">
          <thead>
            <tr className="border-b border-(--color-border) bg-(--color-bg-sidebar) text-left text-(--color-text-muted)">
              {SORT_COLUMNS.map((column) => {
                const active = sortKey === column.key;
                // An active column shows which way it's sorted (ArrowUp for
                // ascending, ArrowDown for descending) instead of the same
                // neutral glyph regardless of direction -- direction was
                // only readable before by clicking and comparing row order.
                const Icon = active ? (data.dir === "desc" ? ArrowDown : ArrowUp) : ArrowUpDown;
                return (
                  <th key={column.key} className="px-3 py-2 font-medium">
                    <button type="button" onClick={() => toggleSort(column.key)} className="flex items-center gap-1 hover:text-(--color-text)">
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
              <tr key={entry.id} className="border-b border-(--color-border) last:border-0 hover:bg-(--color-bg-hover)">
                <td className="px-3 py-2">
                  <Link to={`/r/${entry.id}`} className="font-medium hover:underline">
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
                <td className="px-3 py-2 text-(--color-text-muted)">{entry.trust_phrase}</td>
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
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-(--color-text-faint)">Skills</h2>
          <div className="space-y-1">
            {data.skills.map((skill) => (
              <Link key={skill.name} to={`/s/${skill.name}`} className="block rounded-md px-2 py-1.5 text-sm hover:bg-(--color-bg-hover)">
                {skill.name}
              </Link>
            ))}
          </div>
        </section>
      )}

      {data.broken.length > 0 && (
        <section className="mt-10">
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-(--color-text-faint)">
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
