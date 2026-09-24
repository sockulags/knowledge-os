import { useState, type ReactNode } from "react";
import { useParams, Link } from "react-router";
import { ChevronRight, FilePlus, FolderPlus, Scale } from "lucide-react";
import { api } from "../api/client";
import type { GroupPayload, RecordSummary } from "../api/types";
import { useApi } from "../hooks/useApi";
import { PageSkeleton } from "../components/Skeleton";
import { Breadcrumb } from "../components/Breadcrumb";
import { PropertiesBlock } from "../components/PropertiesBlock";
import { TechnicalDetails } from "../components/TechnicalDetails";
import { Markdown } from "../components/Markdown";
import { Pill } from "../components/Pill";
import { EmptyState } from "../components/EmptyState";
import { LoadError } from "../components/Callout";
import { ProjectPageTree } from "../components/ProjectTree";
import { useShell } from "../components/Shell";
import { useStructure } from "../components/Structure";
import { loadErrorMessage } from "../lib/language";
import { useDocumentTitle } from "../hooks/useDocumentTitle";

function GroupSection({ group }: { group: GroupPayload }) {
  return (
    <section className="mt-6">
      <h3 className="kos-eyebrow mb-2.5">{group.header}</h3>
      {group.records.length === 0 ? (
        <p className="text-sm text-(--color-text-faint)">{group.empty_text}</p>
      ) : (
        <div className="space-y-1.5">
          {group.records.map((record) => (
            <Link
              key={record.id}
              to={`/r/${record.id}`}
              className="kos-card flex items-center justify-between gap-3 px-3.5 py-2.5"
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">{record.title}</p>
                {record.sentence && <p className="mt-0.5 truncate text-xs text-(--color-text-muted)">{record.sentence}</p>}
              </div>
              <Pill pill={record.status_pill} />
            </Link>
          ))}
        </div>
      )}
    </section>
  );
}

function RecordRowList({ records }: { records: RecordSummary[] }) {
  return (
    <div className="space-y-1">
      {records.map((record) => (
        <Link
          key={record.id}
          to={`/r/${record.id}`}
          className="kos-row justify-between px-2 py-1.5 text-sm"
        >
          <span className="min-w-0 truncate">{record.title}</span>
          <Pill pill={record.status_pill} />
        </Link>
      ))}
    </div>
  );
}

function Collapsible({ title, defaultOpen, children }: { title: string; defaultOpen: boolean; children: ReactNode }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section className="mt-8">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="kos-eyebrow mb-2.5 flex items-center gap-1.5 rounded-(--radius-control) hover:text-(--color-text-muted)"
      >
        <ChevronRight size={13} className={open ? "rotate-90 transition-transform duration-100" : "transition-transform duration-100"} />
        {title}
      </button>
      {open && children}
    </section>
  );
}

export function Project() {
  const { projectId } = useParams<{ projectId: string }>();
  const apiState = useApi(() => api.project(projectId!), [projectId]);
  const { data, loading, notFound } = apiState;
  const structure = useStructure();
  const { nav } = useShell();
  useDocumentTitle(nav?.workspace_name, data?.title ?? null);

  if (loading) return <PageSkeleton />;
  if (notFound)
    return <EmptyState title="Project not found" body={`No project named "${projectId}" exists in this workspace.`} />;
  if (apiState.error || !data)
    return <LoadError>{loadErrorMessage(apiState, nav?.language, "Could not load this project.")}</LoadError>;

  const treeHasContent = data.tree.records.length > 0 || data.tree.children.length > 0 || data.tree.broken.length > 0;
  // The project's short name, as the sidebar shows it.
  const projectName = nav?.projects.find((project) => project.id === data.id)?.title ?? data.title;

  return (
    <div className="mx-auto w-full max-w-[760px] px-6 py-12 sm:px-10">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <Breadcrumb items={data.breadcrumb} />
        <div className="no-print ml-auto flex items-center gap-1">
          <Link
            to={`/p/${data.id}/new`}
            className="kos-btn kos-btn-ghost kos-btn-sm"
          >
            <FilePlus size={14} />
            New page
          </Link>
          <button
            type="button"
            onClick={() => structure.newFolder(data.id, "", projectName)}
            className="kos-btn kos-btn-ghost kos-btn-sm"
          >
            <FolderPlus size={14} />
            New folder
          </button>
          <Link
            to={`/p/${data.id}/new?kind=decision`}
            className="kos-btn kos-btn-ghost kos-btn-sm"
          >
            <Scale size={14} />
            Propose a decision
          </Link>
        </div>
      </div>
      <h1 className="kos-title">{data.title}</h1>

      <div className="mt-6">
        <PropertiesBlock properties={data.properties} />
      </div>
      <TechnicalDetails details={data.technical_details} />

      <GroupSection group={data.groups.governing} />
      <GroupSection group={data.groups.proposed} />
      <GroupSection group={data.groups.historical} />

      {data.overview_body_html && (
        <div className="mt-10">
          <Markdown html={data.overview_body_html} />
        </div>
      )}

      {treeHasContent && (
        <section className="mt-10">
          <h3 className="kos-eyebrow mb-2.5">
            Pages in this project
          </h3>
          <ProjectPageTree projectId={data.id} projectTitle={projectName} tree={data.tree} />
        </section>
      )}

      <Collapsible title={data.observations.header} defaultOpen={data.observations.records.length > 0}>
        {data.observations.records.length === 0 ? (
          <p className="text-sm text-(--color-text-faint)">{data.observations.empty_text}</p>
        ) : (
          <RecordRowList records={data.observations.records} />
        )}
      </Collapsible>

      <Collapsible title={data.raw_material.header} defaultOpen={data.raw_material.records.length > 0}>
        {data.raw_material.records.length === 0 ? (
          <p className="text-sm text-(--color-text-faint)">{data.raw_material.empty_text}</p>
        ) : (
          <RecordRowList records={data.raw_material.records} />
        )}
      </Collapsible>

      {(data.related_general.records.length > 0 || data.related_skills.length > 0) && (
        <section className="mt-8">
          <h3 className="kos-eyebrow mb-2.5">
            {data.related_general.header}
          </h3>
          <RecordRowList records={data.related_general.records} />
          {data.related_skills.length > 0 && (
            <div className="mt-1 space-y-1">
              {data.related_skills.map((skill) => (
                <Link
                  key={skill.name}
                  to={`/s/${skill.name}`}
                  className="kos-row px-2 py-1.5 text-sm"
                >
                  {skill.name}
                </Link>
              ))}
            </div>
          )}
        </section>
      )}
    </div>
  );
}
