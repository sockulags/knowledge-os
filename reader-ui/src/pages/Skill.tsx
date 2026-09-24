import { useParams, Link } from "react-router";
import { AlertTriangle } from "lucide-react";
import { api } from "../api/client";
import { useApi } from "../hooks/useApi";
import { PageSkeleton } from "../components/Skeleton";
import { Breadcrumb } from "../components/Breadcrumb";
import { Markdown } from "../components/Markdown";
import { TableOfContents } from "../components/TableOfContents";
import { EmptyState } from "../components/EmptyState";
import { Callout, LoadError } from "../components/Callout";
import { useShell } from "../components/Shell";
import { loadErrorMessage } from "../lib/language";
import { useDocumentTitle } from "../hooks/useDocumentTitle";

export function Skill() {
  const { skillName } = useParams<{ skillName: string }>();
  const { nav } = useShell();
  const apiState = useApi(() => api.skill(skillName!), [skillName]);
  const { data, loading, notFound } = apiState;
  useDocumentTitle(nav?.workspace_name, data?.title ?? data?.name ?? null);

  if (loading) return <PageSkeleton />;
  if (notFound)
    return <EmptyState title="No such skill" body={`No skill named "${skillName}" exists in this workspace.`} />;
  if (apiState.error || !data)
    return <LoadError>{loadErrorMessage(apiState, nav?.language, "Could not load this skill.")}</LoadError>;

  if (data.broken) {
    return (
      <div className="mx-auto w-full max-w-[720px] px-6 py-12 sm:px-10">
        <h1 className="kos-title">{data.broken.label}</h1>
        <div className="mt-6">
          <Callout tone="danger">{data.broken.detail}</Callout>
        </div>
      </div>
    );
  }

  const showToc = (data.headings?.length ?? 0) >= 3;

  return (
    <div className="mx-auto flex w-full max-w-[1100px] gap-10 px-6 py-12 sm:px-10">
      <div className="mx-auto w-full max-w-[720px]">
        <Breadcrumb items={[{ label: "Skills", href: "/everything" }]} current={data.title ?? data.name} />
        <h1 className="kos-title">{data.title ?? data.name}</h1>
        {data.description && <p className="kos-lede">{data.description}</p>}

        <dl className="kos-card mt-6 mb-8 divide-y divide-(--color-border) px-4 py-0.5">
          <div className="grid grid-cols-[100px_1fr] gap-3 py-2 text-sm sm:grid-cols-[124px_1fr]">
            <dt className="text-(--color-text-faint)">Trust</dt>
            <dd>{data.trust_label}</dd>
          </div>
          <div className="grid grid-cols-[100px_1fr] gap-3 py-2 text-sm sm:grid-cols-[124px_1fr]">
            <dt className="text-(--color-text-faint)">Tags</dt>
            <dd>
              {data.tags && data.tags.length > 0 ? (
                <div className="flex flex-wrap gap-1.5">
                  {data.tags.map((tag) => (
                    <span key={tag} className="rounded-[5px] bg-(--color-bg-hover) px-1.5 py-0.5 text-xs text-(--color-text-muted)">
                      {tag}
                    </span>
                  ))}
                </div>
              ) : (
                <span className="text-(--color-text-faint)">No tags recorded.</span>
              )}
            </dd>
          </div>
        </dl>

        {data.body_html && <Markdown html={data.body_html} />}

        {data.references && data.references.length > 0 && (
          <section className="mt-10 border-t border-(--color-border) pt-6">
            <h3 className="kos-eyebrow mb-2.5">
              Supporting references
            </h3>
            <div className="space-y-1">
              {data.references.map((reference) =>
                reference.readable ? (
                  <Link
                    key={reference.path}
                    to={reference.href!}
                    className="kos-row px-2 py-1.5 text-sm"
                  >
                    {reference.title}
                  </Link>
                ) : (
                  <div key={reference.path} className="flex items-center gap-2 px-2 py-1.5 text-sm text-(--color-text-faint)">
                    <AlertTriangle size={13} />
                    {reference.title}
                  </div>
                ),
              )}
            </div>
          </section>
        )}
      </div>
      {showToc && data.headings && <TableOfContents headings={data.headings} />}
    </div>
  );
}
