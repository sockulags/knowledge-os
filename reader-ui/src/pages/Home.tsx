import { useEffect, useState } from "react";
import { Link } from "react-router";
import { ArrowRight, FolderKanban } from "lucide-react";
import { api } from "../api/client";
import type { HealthSummary } from "../api/types";
import { useApi } from "../hooks/useApi";
import { PageSkeleton } from "../components/Skeleton";
import { Pill } from "../components/Pill";
import { Callout } from "../components/Callout";

export function Home() {
  const { data, loading, error } = useApi(() => api.home(), []);
  const [health, setHealth] = useState<HealthSummary | null>(null);

  useEffect(() => {
    api
      .workspace()
      .then((w) => setHealth(w.health))
      .catch(() => setHealth(null));
  }, []);

  if (loading) return <PageSkeleton />;
  if (error || !data) return <Callout tone="danger">{error ?? "Could not load the home page."}</Callout>;

  const somethingWrong = health && (!health.lint_ok || health.search_disabled);

  return (
    <div className="mx-auto w-full max-w-[760px] px-6 py-12 sm:px-10">
      <h1 className="text-[28px] sm:text-[36px] font-semibold leading-tight tracking-tight">{data.title}</h1>
      <p className="mt-1.5 text-(--color-text-muted)">{data.subtitle}</p>

      {somethingWrong && health && (
        <div className="mt-6">
          <Callout tone="danger">
            <p>{!health.lint_ok ? health.lint_message : health.search_disabled_reason}</p>
            {health.search_disabled_reason?.includes("kos index") && (
              <code className="mt-1 inline-block rounded bg-(--color-bg-hover) px-2 py-0.5 font-mono text-xs">
                kos index
              </code>
            )}
          </Callout>
        </div>
      )}

      {data.waiting_on_you.length > 0 && (
        <section className="mt-10">
          <div className="mb-3 flex items-baseline justify-between gap-3">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-(--color-text-faint)">
              {data.sections.waiting_on_you}
            </h2>
            <Link to="/decide" className="text-sm text-(--color-text-muted) underline-offset-2 hover:text-(--color-text) hover:underline">
              {data.decide_link}
            </Link>
          </div>
          <div className="space-y-2">
            {data.waiting_on_you.map((record) => (
              <Link
                key={record.id}
                to={`/r/${record.id}`}
                className="flex items-center justify-between gap-3 rounded-lg border border-(--color-border) bg-(--color-bg-raised) px-4 py-3 hover:border-(--color-border-strong)"
              >
                <div className="min-w-0">
                  <p className="truncate font-medium">{record.title}</p>
                  <p className="text-sm text-(--color-text-muted)">{record.sentence}</p>
                </div>
                <Pill pill={record.status_pill} />
              </Link>
            ))}
          </div>
        </section>
      )}

      {data.in_force.length > 0 && (
        <section className="mt-10">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-(--color-text-faint)">{data.sections.in_force}</h2>
          <div className="space-y-1">
            {data.in_force.map((record) => (
              <Link
                key={record.id}
                to={`/r/${record.id}`}
                className="flex items-center justify-between gap-3 rounded-md px-3 py-2 hover:bg-(--color-bg-hover)"
              >
                <span className="min-w-0 truncate">{record.title}</span>
                <span className="shrink-0 text-sm text-(--color-text-faint)">{record.accepted_display}</span>
              </Link>
            ))}
          </div>
        </section>
      )}

      {data.recently_changed.length > 0 && (
        <section className="mt-10">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-(--color-text-faint)">
            {data.sections.recently_changed}
          </h2>
          <div className="space-y-1">
            {data.recently_changed.map((record) => (
              <Link
                key={record.id}
                to={`/r/${record.id}`}
                className="flex items-center justify-between gap-3 rounded-md px-3 py-1.5 text-sm hover:bg-(--color-bg-hover)"
              >
                <span className="min-w-0 truncate text-(--color-text)">{record.title}</span>
                <span className="shrink-0 text-(--color-text-faint)" title={record.updated_exact ?? undefined}>
                  {record.updated_display}
                </span>
              </Link>
            ))}
          </div>
        </section>
      )}

      {data.projects.length > 0 && (
        <section className="mt-10">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-(--color-text-faint)">{data.sections.projects}</h2>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {data.projects.map((project) => (
              <Link
                key={project.id}
                to={`/p/${project.id}`}
                className="group flex items-center justify-between gap-3 rounded-lg border border-(--color-border) bg-(--color-bg-raised) px-4 py-4 hover:border-(--color-border-strong)"
              >
                <span className="flex items-center gap-2.5 font-medium">
                  <FolderKanban size={16} className="text-(--color-text-faint)" />
                  {project.title}
                </span>
                <ArrowRight
                  size={15}
                  className="text-(--color-text-faint) transition-transform group-hover:translate-x-0.5"
                />
              </Link>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
