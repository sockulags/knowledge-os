// Runs under Node's built-in test runner (`npm test`).

import assert from "node:assert/strict";
import { afterEach, beforeEach, describe, it } from "node:test";

interface Call {
  url: string;
  init?: RequestInit;
}

let calls: Call[];
let events: string[];
let replies: Array<(call: Call) => Response>;
let fresh = 0;

/** Each test gets its own copy of the module, so no write token carries over. */
async function loadModule(): Promise<typeof import("./write.ts")> {
  fresh += 1;
  return import(`./write.ts?test=${fresh}`);
}

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function session(token: string): () => Response {
  return () => json(200, { write_token: token, write_token_header: "X-KOS-Write-Token" });
}

beforeEach(() => {
  calls = [];
  events = [];
  replies = [];
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const call = { url: String(input), init };
    calls.push(call);
    const reply = replies.shift();
    if (reply === undefined) throw new Error(`unexpected request to ${call.url}`);
    return reply(call);
  }) as typeof fetch;
  (globalThis as { window?: unknown }).window = {
    dispatchEvent: (event: Event) => {
      events.push(event.type);
      return true;
    },
  };
});

afterEach(() => {
  delete (globalThis as { window?: unknown }).window;
});

const header = (call: Call) => (call.init?.headers as Record<string, string>)["X-KOS-Write-Token"];

describe("send", () => {
  it("fetches a new token after a 403 about the header and retries once", async () => {
    const { send } = await loadModule();
    replies.push(
      session("old"),
      () => json(403, { error: "forbidden", detail: "missing or wrong write token header" }),
      session("new"),
      () => json(200, { done: true }),
    );
    const outcome = await send("POST", "/api/sync", {});
    assert.deepEqual(outcome, { ok: true, data: { done: true } });
    assert.deepEqual(
      calls.map((call) => call.url),
      ["/api/session", "/api/sync", "/api/session", "/api/sync"],
    );
    assert.equal(header(calls[1]), "old");
    assert.equal(header(calls[3]), "new");
  });

  it("gives up after one retry", async () => {
    const { send } = await loadModule();
    const refused = () => json(403, { error: "forbidden", detail: "wrong write token header" });
    replies.push(session("a"), refused, session("b"), refused);
    const outcome = await send("POST", "/api/sync", {});
    assert.equal(outcome.ok, false);
    assert.equal(outcome.ok ? 0 : outcome.status, 403);
    assert.equal(calls.length, 4);
    assert.deepEqual(events, []);
  });

  it("sends a keepalive request without waiting for the session once it has loaded", async () => {
    const { send, prepareSession } = await loadModule();
    replies.push(session("t"));
    prepareSession();
    await new Promise((resolve) => setTimeout(resolve, 0));
    replies.push(() => json(200, {}));
    const pending = send("POST", "/api/records/a/accept", { expected_sha256: "x" }, false, { keepalive: true });
    // The write is handed to fetch synchronously, before any await.
    assert.equal(calls.length, 2);
    assert.equal(calls[1].init?.keepalive, true);
    assert.equal(header(calls[1]), "t");
    await pending;
  });

  it("signals a write but not a preview", async () => {
    const { write, WRITE_EVENT } = await loadModule();
    replies.push(session("t"), () => json(200, { html: "<p>x</p>" }));
    const preview = await write.preview("x");
    assert.equal(preview.ok, true);
    assert.deepEqual(events, []);

    replies.push(() => json(200, { id: "a" }));
    await write.create({ metadata: {}, body: "x" });
    assert.deepEqual(events, [WRITE_EVENT]);
  });

  it("does not signal for semantic search or a remote check", async () => {
    const { semanticSearch, syncSetup } = await loadModule();
    replies.push(session("t"), () => json(200, {}), () => json(200, {}), () => json(200, {}));
    await semanticSearch.install();
    await semanticSearch.refresh();
    await syncSetup.check("https://example.invalid/repo.git");
    assert.equal(calls.length, 4);
    assert.deepEqual(events, []);
  });
});
