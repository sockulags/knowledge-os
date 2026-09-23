// Writes to the local core. Every write carries the per-process token from
// GET /api/session in the header that response names, with a JSON body; the
// core refuses anything else (see "Local interface write API" in
// docs/architecture.md). Failures come back as data, not exceptions, so a
// page can show a conflict, lint issues, or a refusal in place.

import type { ResolveResult, SupersedeResult, SyncResult, SyncStatus, WriteFailure, WriteResult } from "./types";

interface Session {
  token: string;
  header: string;
}

let session: Promise<Session> | null = null;

function loadSession(): Promise<Session> {
  if (session === null) {
    session = fetch("/api/session")
      .then(async (response) => {
        if (!response.ok) throw new Error(`The core refused to hand out a write token (${response.status}).`);
        const body = (await response.json()) as { write_token: string; write_token_header: string };
        return { token: body.write_token, header: body.write_token_header };
      })
      .catch((error: unknown) => {
        session = null; // try again on the next write
        throw error;
      });
  }
  return session;
}

/** Dispatched on `window` after every successful write. */
export const WRITE_EVENT = "kos:write";

export type Outcome<T> = { ok: true; data: T } | { ok: false; status: number; failure: WriteFailure };

export async function send<T>(method: "POST" | "PATCH", path: string, body: unknown, retried = false): Promise<Outcome<T>> {
  let current: Session;
  try {
    current = await loadSession();
  } catch (error) {
    const detail = error instanceof Error ? error.message : "Could not reach the core.";
    return { ok: false, status: 0, failure: { error: "unavailable", detail } };
  }
  let response: Response;
  try {
    response = await fetch(path, {
      method,
      headers: { "Content-Type": "application/json", [current.header]: current.token },
      body: JSON.stringify(body),
    });
  } catch {
    return { ok: false, status: 0, failure: { error: "unavailable", detail: "Could not reach the core. Is it still running?" } };
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
    return send<T>(method, path, body, true);
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
  accept: (id: string, expectedSha256: string) =>
    send<WriteResult>("POST", `${recordPath(id)}/accept`, { expected_sha256: expectedSha256 }),
  withdraw: (id: string, expectedSha256: string, reason: string) =>
    send<WriteResult>("POST", `${recordPath(id)}/withdraw`, { expected_sha256: expectedSha256, reason }),
  supersede: (id: string, expectedSha256: string, oldId: string, oldExpectedSha256: string) =>
    send<SupersedeResult>("POST", `${recordPath(id)}/supersede`, {
      expected_sha256: expectedSha256,
      old_id: oldId,
      old_expected_sha256: oldExpectedSha256,
    }),
  preview: (body: string, path?: string) => send<{ html: string }>("POST", "/api/preview", { body, path }),
};

/** Git sync (see "Git sync API" in docs/architecture.md). A failed sync
 * carries the fresh repository status, and a stopped pull its conflicts. */
export const sync = {
  run: () => send<SyncResult>("POST", "/api/sync", {}),
  resolve: (path: string, choice: "ours" | "theirs" | "merged", content?: string) =>
    send<ResolveResult>("POST", "/api/sync/resolve", { path, choice, content }),
  abort: () => send<{ status: SyncStatus }>("POST", "/api/sync/abort", {}),
};

/** A provenance reference for something done in this interface, matching the
 * core's own `interface:<UTC timestamp>:<action>` references. */
export function interfaceReference(action: string, now = new Date()): string {
  return `interface:${now.toISOString().replace(/\.\d{3}Z$/, "Z")}:${action}`;
}
