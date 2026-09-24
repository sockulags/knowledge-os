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
  SyncSetup,
  SyncStatus,
  WorkspacePayload,
} from "./types";

export class ApiNotFoundError extends Error {
  constructor(detail: string) {
    super(detail);
    this.name = "ApiNotFoundError";
  }
}

/** Thrown instead of the browser's own fetch failure (e.g. the raw "Failed
 * to fetch"/"NetworkError") when a request never reached the core at all --
 * the process is not running, or was just restarted. Callers show
 * `networkErrorMessage(nav?.language)` (see lib/language.ts) rather than
 * this error's own message. */
export class ApiUnreachableError extends Error {
  constructor() {
    super("Could not reach the core.");
    this.name = "ApiUnreachableError";
  }
}

async function request<T>(path: string, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, { signal });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiUnreachableError();
  }
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
  search: (query: string, signal?: AbortSignal) => request<SearchPayload>(`/api/search${query}`, signal),
  everything: (query: string) => request<EverythingPayload>(`/api/everything${query}`),
  syncStatus: () => request<SyncStatus>("/api/sync/status"),
  syncConflicts: () => request<ConflictsPayload>("/api/sync/conflicts"),
  syncSetup: () => request<SyncSetup>("/api/sync/setup"),
};
