import { useState, type ReactNode } from "react";
import { useParams, Link } from "react-router";
import { ChevronRight } from "lucide-react";
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
import { Callout } from "../components/Callout";
import { TreeNodeView } from "../components/ProjectTree";

function GroupSection({ group }: { group: GroupPayload }) {
  return (
    <section className="mt-6">
      <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-(--color-text-faint)">
        {group.header}
      </h3>
      {group.records.length === 0 ? (
        <p className="text-sm italic text-(--color-text-faint)">{group.empty_text}</p>
      ) : (
        <div className="space-y-1.5">
          {group.records.map((record) => (
            <Link
              key={record.id}
              to={`/r/${record.id}`}
              className="flex items-center justify-between gap-3 rounded-lg border border-(--color-border) bg-(--color-bg-raised) px-3.5 py-2.5 hover:border-(--color-border-strong)"
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">{record.title}</p>
                {record.sentence && <p className="truncate text-xs text-(--color-text-muted)">{record.sentence}</p>}
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
          className="flex items-center justify-between gap-3 rounded-md px-2 py-1.5 text-sm hover:bg-(--color-bg-hover)"
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
        className="mb-2 flex items-center gap-1.5 text-sm font-semibold uppercase tracking-wide text-(--color-text-faint) hover:text-(--color-text-muted)"
      >
        <ChevronRight size={13} className={open ? "rotate-90 transition-transform" : "transition-transform"} />
        {title}
      </button>
      {open && children}
    </section>
  );
}

export function Project() {
  const { projectId } = useParams<{ projectId: string }>();
  const { data, loading, notFound, error } = useApi(() => api.project(projectId!), [projectId]);

  if (loading) return <PageSkeleton />;
  if (notFound)
    return <EmptyState title="Project not found" body={`No project named "${projectId}" exists in this workspace.`} />;
  if (error || !data) return <Callout tone="danger">{error ?? "Could not load this project."}</Callout>;

  const treeHasContent = data.tree.records.length > 0 || data.tree.children.length > 0 || data.tree.broken.length > 0;

  return (
    <div className="mx-auto w-full max-w-[760px] px-6 py-12 sm:px-10">
      <Breadcrumb items={data.breadcrumb} />
      <h1 className="text-[36px] font-semibold leading-tight tracking-tight">{data.title}</h1>

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
          <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-(--color-text-faint)">
            Pages in this project
          </h3>
          <div className="rounded-lg border border-(--color-border) bg-(--color-bg-raised) p-2">
            {data.tree.records.map((record) => (
              <TreeNodeView key={record.id} node={{ name: record.title, overview: record, records: [], broken: [], children: [] }} depth={0} />
            ))}
            {data.tree.children.map((child) => (
              <TreeNodeView key={child.name} node={child} depth={0} />
            ))}
          </div>
        </section>
      )}

      <Collapsible title={data.observations.header} defaultOpen={data.observations.records.length > 0}>
        {data.observations.records.length === 0 ? (
          <p className="text-sm italic text-(--color-text-faint)">{data.observations.empty_text}</p>
        ) : (
          <RecordRowList records={data.observations.records} />
        )}
      </Collapsible>

      <Collapsible title={data.raw_material.header} defaultOpen={data.raw_material.records.length > 0}>
        {data.raw_material.records.length === 0 ? (
          <p className="text-sm italic text-(--color-text-faint)">{data.raw_material.empty_text}</p>
        ) : (
          <RecordRowList records={data.raw_material.records} />
        )}
      </Collapsible>

      {(data.related_general.records.length > 0 || data.related_skills.length > 0) && (
        <section className="mt-8">
          <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-(--color-text-faint)">
            {data.related_general.header}
          </h3>
          <RecordRowList records={data.related_general.records} />
          {data.related_skills.length > 0 && (
            <div className="mt-1 space-y-1">
              {data.related_skills.map((skill) => (
                <Link
                  key={skill.name}
                  to={`/s/${skill.name}`}
                  className="block rounded-md px-2 py-1.5 text-sm hover:bg-(--color-bg-hover)"
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
