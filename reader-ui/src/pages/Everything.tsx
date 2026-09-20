import { useMemo, useState } from "react";
import { Link } from "react-router";
import { ArrowUpDown } from "lucide-react";
import { api } from "../api/client";
import { useApi } from "../hooks/useApi";
import { PageSkeleton } from "../components/Skeleton";
import { Callout, BrokenRecordCallout } from "../components/Callout";
import { Pill } from "../components/Pill";
import type { EverythingEntry } from "../api/types";

type SortKey = "title" | "type_label" | "updated" | "project_title";

function sortEntries(entries: EverythingEntry[], key: SortKey, direction: 1 | -1): EverythingEntry[] {
  return [...entries].sort((a, b) => {
    const left = (a[key] ?? "") as string;
    const right = (b[key] ?? "") as string;
    return left.localeCompare(right) * direction;
  });
}

export function Everything() {
  const { data, loading, error } = useApi(() => api.everything(), []);
  const [sortKey, setSortKey] = useState<SortKey>("title");
  const [direction, setDirection] = useState<1 | -1>(1);
  const [typeFilter, setTypeFilter] = useState("");
  const [projectFilter, setProjectFilter] = useState("");

  const types = useMemo(() => {
    if (!data) return [];
    return Array.from(new Set(data.entries.map((entry) => entry.type_label))).sort();
  }, [data]);
  const projects = useMemo(() => {
    if (!data) return [];
    return Array.from(new Set(data.entries.map((entry) => entry.project_title).filter((v): v is string => Boolean(v)))).sort();
  }, [data]);

  const rows = useMemo(() => {
    if (!data) return [];
    let entries = data.entries;
    if (typeFilter) entries = entries.filter((entry) => entry.type_label === typeFilter);
    if (projectFilter) entries = entries.filter((entry) => entry.project_title === projectFilter);
    return sortEntries(entries, sortKey, direction);
  }, [data, typeFilter, projectFilter, sortKey, direction]);

  function toggleSort(key: SortKey) {
    if (key === sortKey) setDirection((d) => (d === 1 ? -1 : 1));
    else {
      setSortKey(key);
      setDirection(1);
    }
  }

  if (loading) return <PageSkeleton />;
  if (error || !data) return <Callout tone="danger">{error ?? "Could not load the catalog."}</Callout>;

  const columns: { key: SortKey; label: string }[] = [
    { key: "title", label: "Title" },
    { key: "type_label", label: "Kind" },
    { key: "updated", label: "Updated" },
  ];

  return (
    <div className="mx-auto w-full max-w-[1100px] px-6 py-12 sm:px-10">
      <h1 className="text-[26px] sm:text-[32px] font-semibold leading-tight tracking-tight">Everything</h1>
      <p className="mt-1.5 text-(--color-text-muted)">
        Every record, source, and discovery the workspace holds, in one flat list.
      </p>

      <div className="mt-5 flex flex-wrap gap-2">
        <select
          value={typeFilter}
          onChange={(event) => setTypeFilter(event.target.value)}
          className="rounded-md border border-(--color-border) bg-(--color-bg) px-2.5 py-1.5 text-sm text-(--color-text-muted)"
        >
          <option value="">Kind: Any</option>
          {types.map((type) => (
            <option key={type} value={type}>
              {type}
            </option>
          ))}
        </select>
        {projects.length > 0 && (
          <select
            value={projectFilter}
            onChange={(event) => setProjectFilter(event.target.value)}
            className="rounded-md border border-(--color-border) bg-(--color-bg) px-2.5 py-1.5 text-sm text-(--color-text-muted)"
          >
            <option value="">Project: Any</option>
            {projects.map((project) => (
              <option key={project} value={project}>
                {project}
              </option>
            ))}
          </select>
        )}
      </div>

      <div className="mt-6 overflow-x-auto rounded-lg border border-(--color-border)">
        <table className="w-full min-w-[720px] border-collapse text-sm">
          <thead>
            <tr className="border-b border-(--color-border) bg-(--color-bg-sidebar) text-left text-(--color-text-muted)">
              {columns.map((column) => (
                <th key={column.key} className="px-3 py-2 font-medium">
                  <button type="button" onClick={() => toggleSort(column.key)} className="flex items-center gap-1 hover:text-(--color-text)">
                    {column.label}
                    <ArrowUpDown size={12} className={sortKey === column.key ? "opacity-100" : "opacity-30"} />
                  </button>
                </th>
              ))}
              <th className="px-3 py-2 font-medium">Status</th>
              <th className="px-3 py-2 font-medium">Trust</th>
              <th className="px-3 py-2 font-medium">
                <button
                  type="button"
                  onClick={() => toggleSort("project_title")}
                  className="flex items-center gap-1 hover:text-(--color-text)"
                >
                  Project
                  <ArrowUpDown size={12} className={sortKey === "project_title" ? "opacity-100" : "opacity-30"} />
                </button>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((entry) => (
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
                <td className="px-3 py-2">
                  <Pill pill={entry.status_pill} />
                </td>
                <td className="px-3 py-2 text-(--color-text-muted)">{entry.trust_phrase}</td>
                <td className="px-3 py-2 text-(--color-text-muted)">{entry.project_title ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
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
