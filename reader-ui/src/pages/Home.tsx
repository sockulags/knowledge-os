import { useEffect, useState } from "react";
import { Link } from "react-router";
import { ArrowRight, FolderKanban } from "lucide-react";
import { api } from "../api/client";
import type { HealthSummary } from "../api/types";
import { useApi } from "../hooks/useApi";
import { PageSkeleton } from "../components/Skeleton";
import { Pill } from "../components/Pill";
import { Callout, LoadError } from "../components/Callout";
import { useShell } from "../components/Shell";
import { loadErrorMessage } from "../lib/language";

export function Home() {
  const { nav } = useShell();
  const apiState = useApi(() => api.home(), []);
  const { data, loading } = apiState;
  const [health, setHealth] = useState<HealthSummary | null>(null);

  useEffect(() => {
    api
      .workspace()
      .then((w) => setHealth(w.health))
      .catch(() => setHealth(null));
  }, []);

  if (loading) return <PageSkeleton />;
  if (apiState.error || !data)
    return <LoadError>{loadErrorMessage(apiState, nav?.language, "Could not load the home page.")}</LoadError>;

  const somethingWrong = health && (!health.lint_ok || health.search_disabled);

  return (
    <div className="mx-auto w-full max-w-[760px] px-6 py-12 sm:px-10">
      <h1 className="kos-title">{data.title}</h1>
      <p className="kos-lede">{data.subtitle}</p>

      {somethingWrong && health && (
        <div className="mt-6">
          <Callout tone="danger">
            <p>{!health.lint_ok ? health.lint_message : health.search_disabled_reason}</p>
            {health.search_disabled_reason?.includes("kos index") && (
              <code className="kos-code mt-1 inline-block">
                kos index
              </code>
            )}
          </Callout>
        </div>
      )}

      {data.waiting_on_you.length > 0 && (
        <section className="mt-10">
          <div className="mb-3 flex items-baseline justify-between gap-3">
            <h2 className="kos-eyebrow">
              {data.sections.waiting_on_you}
            </h2>
            <Link
              to="/decide"
              className="rounded-(--radius-control) text-sm font-medium text-(--color-accent-text) underline-offset-[3px] hover:underline"
            >
              {data.decide_link}
            </Link>
          </div>
          <div className="space-y-2">
            {data.waiting_on_you.map((record) => (
              <Link
                key={record.id}
                to={`/r/${record.id}`}
                className="kos-card flex items-center justify-between gap-3 px-4 py-3"
              >
                <div className="min-w-0">
                  <p className="truncate font-medium">{record.title}</p>
                  <p className="mt-0.5 text-sm text-(--color-text-muted)">{record.sentence}</p>
                </div>
                <Pill pill={record.status_pill} />
              </Link>
            ))}
          </div>
        </section>
      )}

      {data.in_force.length > 0 && (
        <section className="mt-10">
          <h2 className="kos-eyebrow mb-3">{data.sections.in_force}</h2>
          <div className="divide-y divide-(--color-border) border-y border-(--color-border)">
            {data.in_force.map((record) => (
              <Link
                key={record.id}
                to={`/r/${record.id}`}
                className="flex items-center justify-between gap-3 px-3 py-2.5 transition-colors hover:bg-(--color-bg-hover)"
              >
                <span className="min-w-0 truncate">{record.title}</span>
                <span className="shrink-0 text-sm text-(--color-text-faint) tabular-nums">{record.accepted_display}</span>
              </Link>
            ))}
          </div>
        </section>
      )}

      {data.recently_changed.length > 0 && (
        <section className="mt-10">
          <h2 className="kos-eyebrow mb-3">
            {data.sections.recently_changed}
          </h2>
          <div className="space-y-1">
            {data.recently_changed.map((record) => (
              <Link
                key={record.id}
                to={`/r/${record.id}`}
                className="kos-row justify-between px-3 py-1.5 text-sm"
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
          <h2 className="kos-eyebrow mb-3">{data.sections.projects}</h2>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {data.projects.map((project) => (
              <Link
                key={project.id}
                to={`/p/${project.id}`}
                className="kos-card group flex items-center justify-between gap-3 px-4 py-4"
              >
                <span className="flex items-center gap-2.5 font-medium">
                  <FolderKanban size={16} className="text-(--color-accent-text)" />
                  {project.title}
                </span>
                <ArrowRight
                  size={15}
                  className="text-(--color-text-faint) transition-transform duration-100 group-hover:translate-x-0.5 group-hover:text-(--color-accent-text)"
                />
              </Link>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
