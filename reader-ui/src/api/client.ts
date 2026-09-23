// A thin fetch wrapper. Every call hits a same-origin /api/* route (proxied
// by Vite in dev, served by the same Starlette process in production), so
// there is no base URL to configure and no CORS handling needed.

import type {
  ComparePayload,
  DecidePayload,
  DocPayload,
  EverythingPayload,
  HomePayload,
  NavPayload,
  ProjectPayload,
  RecordPayload,
  SearchPayload,
  SkillPayload,
  ConflictsPayload,
  SyncStatus,
  WorkspacePayload,
} from "./types";

export class ApiNotFoundError extends Error {
  constructor(detail: string) {
    super(detail);
    this.name = "ApiNotFoundError";
  }
}

async function request<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (response.status === 404) {
    const body = await response.json().catch(() => ({ detail: "Not found." }));
    throw new ApiNotFoundError(body.detail ?? "Not found.");
  }
  if (!response.ok) {
    throw new Error(`Request to ${path} failed with status ${response.status}`);
  }
  return (await response.json()) as T;
}

export const api = {
  workspace: () => request<WorkspacePayload>("/api/workspace"),
  nav: () => request<NavPayload>("/api/nav"),
  home: () => request<HomePayload>("/api/home"),
  proposedDecisions: (project: string | null) =>
    request<DecidePayload>(`/api/decisions/proposed${project ? `?project=${encodeURIComponent(project)}` : ""}`),
  project: (id: string) => request<ProjectPayload>(`/api/projects/${encodeURIComponent(id)}`),
  record: (id: string) => request<RecordPayload>(`/api/records/${encodeURIComponent(id)}`),
  compare: (id: string) => request<ComparePayload>(`/api/records/${encodeURIComponent(id)}/compare`),
  skill: (name: string) => request<SkillPayload>(`/api/skills/${encodeURIComponent(name)}`),
  doc: (path: string) => request<DocPayload>(`/api/docs/${path}`),
  search: (query: string) => request<SearchPayload>(`/api/search${query}`),
  everything: (query: string) => request<EverythingPayload>(`/api/everything${query}`),
  syncStatus: () => request<SyncStatus>("/api/sync/status"),
  syncConflicts: () => request<ConflictsPayload>("/api/sync/conflicts"),
};
