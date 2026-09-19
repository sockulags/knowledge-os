import { useParams } from "react-router";
import { api } from "../api/client";
import { useApi } from "../hooks/useApi";
import { PageSkeleton } from "../components/Skeleton";
import { Breadcrumb } from "../components/Breadcrumb";
import { Markdown } from "../components/Markdown";
import { TableOfContents } from "../components/TableOfContents";
import { EmptyState } from "../components/EmptyState";
import { Callout } from "../components/Callout";

export function RepoDoc() {
  const params = useParams<{ "*": string }>();
  const path = params["*"] ?? "";
  const { data, loading, notFound, error } = useApi(() => api.doc(path), [path]);

  if (loading) return <PageSkeleton />;
  if (notFound) return <EmptyState title="Document not found" body={`No document at "${path}" exists here.`} />;
  if (error || !data) return <Callout tone="danger">{error ?? "Could not load this document."}</Callout>;

  const showToc = data.headings.length >= 3;

  return (
    <div className="mx-auto flex w-full max-w-[1100px] gap-10 px-6 py-12 sm:px-10">
      <div className="mx-auto w-full max-w-[720px]">
        {/* Unlike "Skills" (Skill.tsx), which links to a section that
            actually exists on /everything, there is no dedicated listing
            page for the repository-document tier (it only appears in the
            sidebar) — so this crumb goes to Home rather than pointing at a
            page with nothing matching on it. */}
        <Breadcrumb items={[{ label: "Home", href: "/" }]} current={data.title} />
        <h1 className="text-[36px] font-semibold leading-tight tracking-tight">{data.title}</h1>

        <div className="mt-6">
          <Callout tone="neutral">{data.unmanaged_label}</Callout>
        </div>

        <Markdown html={data.body_html} />
      </div>
      {showToc && <TableOfContents headings={data.headings} />}
    </div>
  );
}
