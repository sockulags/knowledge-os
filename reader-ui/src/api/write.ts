// Writes to the local core. Every write carries the per-process token from
// GET /api/session in the header that response names, with a JSON body; the
// core refuses anything else (see "Local interface write API" in
// docs/architecture.md). Failures come back as data, not exceptions, so a
// page can show a conflict, lint issues, or a refusal in place.

import type {
  ResolveResult,
  StructureResult,
  SupersedeResult,
  SyncConnectResult,
  SyncRemoteCheck,
  SyncResult,
  SyncSetupInitResult,
  SyncSetupResponse,
  SyncStatus,
  WriteFailure,
  WriteResult,
} from "./types";
import { NETWORK_ERROR_FALLBACK } from "../lib/language";

interface Session {
  token: string;
  header: string;
}

let session: Promise<Session> | null = null;
/** The session once it has loaded, so a write can start without awaiting. */
let loaded: Session | null = null;

function loadSession(): Promise<Session> {
  if (session === null) {
    session = fetch("/api/session")
      .then(async (response) => {
        if (!response.ok) throw new Error(`The core refused to hand out a write token (${response.status}).`);
        const body = (await response.json()) as { write_token: string; write_token_header: string };
        loaded = { token: body.write_token, header: body.write_token_header };
        return loaded;
      })
      .catch((error: unknown) => {
        session = null; // try again on the next write
        throw error;
      });
  }
  return session;
}

/** Fetch the write token ahead of time, so a write sent while the page is
 * being closed (see lib/pendingActions.ts) needs no request before its own. */
export function prepareSession(): void {
  void loadSession().catch(() => undefined);
}

/** Dispatched on `window` after every successful write. */
export const WRITE_EVENT = "kos:write";

export type Outcome<T> = { ok: true; data: T } | { ok: false; status: number; failure: WriteFailure };

export interface SendOptions {
  /** Keep the request alive when the page unloads (flushing pending actions). */
  keepalive?: boolean;
}

export async function send<T>(
  method: "POST" | "PATCH",
  path: string,
  body: unknown,
  retried = false,
  options: SendOptions = {},
): Promise<Outcome<T>> {
  let current: Session;
  if (loaded !== null) {
    // No await before fetch: a write started from a `pagehide` handler is
    // handed to the browser before the page goes away.
    current = loaded;
  } else {
    try {
      current = await loadSession();
    } catch {
      return { ok: false, status: 0, failure: { error: "unavailable", detail: NETWORK_ERROR_FALLBACK } };
    }
  }
  let response: Response;
  try {
    response = await fetch(path, {
      method,
      headers: { "Content-Type": "application/json", [current.header]: current.token },
      body: JSON.stringify(body),
      keepalive: options.keepalive === true,
    });
  } catch {
    return { ok: false, status: 0, failure: { error: "unavailable", detail: NETWORK_ERROR_FALLBACK } };
  }
  const payload = await response.json().catch(() => ({ error: "unavailable", detail: `Unexpected response (${response.status}).` }));
  if (response.ok) {
    // The core commits each write to Git; the status line listens for this.
    window.dispatchEvent(new Event(WRITE_EVENT));
    return { ok: true, data: payload as T };
  }
  // A restarted core has a new token; fetch it once and retry.
  if (response.status === 403 && !retried && typeof payload.detail === "string" && payload.detail.includes("header")) {
    session = null;
    loaded = null;
    return send<T>(method, path, body, true, options);
  }
  return { ok: false, status: response.status, failure: payload as WriteFailure };
}

const recordPath = (id: string) => `/api/records/${encodeURIComponent(id)}`;

export interface CreateRequest {
  metadata: Record<string, unknown>;
  body: string;
  project_path?: string;
}

export interface EditRequest {
  expected_sha256: string;
  metadata?: Record<string, unknown>;
  body?: string;
  confirm_non_material?: boolean;
  change_reference?: string;
}

export const write = {
  create: (request: CreateRequest) => send<WriteResult>("POST", "/api/records", request),
  edit: (id: string, request: EditRequest) => send<WriteResult>("PATCH", recordPath(id), request),
  accept: (id: string, expectedSha256: string, options?: SendOptions) =>
    send<WriteResult>("POST", `${recordPath(id)}/accept`, { expected_sha256: expectedSha256 }, false, options),
  /** `reason` is optional; without one the core records a neutral reference. */
  withdraw: (id: string, expectedSha256: string, reason?: string, options?: SendOptions) =>
    send<WriteResult>(
      "POST",
      `${recordPath(id)}/withdraw`,
      reason && reason.trim() ? { expected_sha256: expectedSha256, reason: reason.trim() } : { expected_sha256: expectedSha256 },
      false,
      options,
    ),
  supersede: (id: string, expectedSha256: string, oldId: string, oldExpectedSha256: string, options?: SendOptions) =>
    send<SupersedeResult>(
      "POST",
      `${recordPath(id)}/supersede`,
      { expected_sha256: expectedSha256, old_id: oldId, old_expected_sha256: oldExpectedSha256 },
      false,
      options,
    ),
  preview: (body: string, path?: string) => send<{ html: string }>("POST", "/api/preview", { body, path }),
};

const projectPath = (id: string) => `/api/projects/${encodeURIComponent(id)}`;

export interface FolderMoveRequest {
  path: string;
  to_project?: string;
  to_parent?: string;
  name?: string;
  title?: string;
  allow_scope_change?: boolean;
}

/** Projects, folders, moves, and renames (see "Structure editing" in
 * docs/architecture.md). Each is one commit. */
export const structure = {
  createProject: (id: string, title: string) =>
    send<StructureResult>("POST", "/api/projects", { id, title }),
  createFolder: (projectId: string, path: string, title: string) =>
    send<StructureResult>("POST", `${projectPath(projectId)}/folders`, { path, title }),
  movePage: (id: string, expectedSha256: string, project: string, folder: string, allowScopeChange: boolean) =>
    send<StructureResult>("POST", `${recordPath(id)}/move`, {
      expected_sha256: expectedSha256,
      project,
      folder,
      allow_scope_change: allowScopeChange,
    }),
  renamePage: (id: string, expectedSha256: string, title: string) =>
    send<StructureResult>("POST", `${recordPath(id)}/rename`, { expected_sha256: expectedSha256, title }),
  moveFolder: (projectId: string, request: FolderMoveRequest) =>
    send<StructureResult>("POST", `${projectPath(projectId)}/folders/move`, request),
  /** `expected` is the preview's, so nothing it did not show is deleted. */
  deletePage: (id: string, expectedSha256: string, expected: Record<string, string>) =>
    send<StructureResult>("POST", `${recordPath(id)}/delete`, { expected_sha256: expectedSha256, expected }),
  deleteFolder: (projectId: string, path: string, expected: Record<string, string>) =>
    send<StructureResult>("POST", `${projectPath(projectId)}/folders/delete`, { path, expected }),
};

/** Git sync (see "Git sync API" in docs/architecture.md). A failed sync
 * carries the fresh repository status, and a stopped pull its conflicts. */
export const sync = {
  run: () => send<SyncResult>("POST", "/api/sync", {}),
  resolve: (path: string, choice: "ours" | "theirs" | "merged", content?: string) =>
    send<ResolveResult>("POST", "/api/sync/resolve", { path, choice, content }),
  abort: () => send<{ status: SyncStatus }>("POST", "/api/sync/abort", {}),
};

/** The guided sync setup (issue #56). `url` omitted means the remote the
 * repository already names. Credentials are never sent: Git signs in with
 * the computer's own credential helper or SSH key. */
export const syncSetup = {
  init: (identity?: { name: string; email: string }) =>
    send<SyncSetupInitResult>("POST", "/api/sync/setup/init", identity ?? {}),
  identity: (name: string, email: string) =>
    send<SyncSetupResponse & { identity: { name: string; email: string } }>("POST", "/api/sync/setup/identity", {
      name,
      email,
    }),
  check: (url?: string) => send<SyncSetupResponse & { check: SyncRemoteCheck }>("POST", "/api/sync/setup/check", { url }),
  connect: (url?: string) => send<SyncConnectResult>("POST", "/api/sync/setup/connect", { url }),
};

/** A provenance reference for something done in this interface, matching the
 * core's own `interface:<UTC timestamp>:<action>` references. */
export function interfaceReference(action: string, now = new Date()): string {
  return `interface:${now.toISOString().replace(/\.\d{3}Z$/, "Z")}:${action}`;
}
