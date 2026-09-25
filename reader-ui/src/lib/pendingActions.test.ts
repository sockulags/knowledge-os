// Runs under Node's built-in test runner (`npm test`).

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { isActive, PendingQueue, showsOutcome, type RunOptions, type RunResult } from "./pendingActions.ts";

/** A clock whose timers only fire when the test advances it. */
function fakeClock() {
  let now = 1000;
  let nextHandle = 1;
  const timers = new Map<number, { at: number; callback: () => void }>();
  return {
    now: () => now,
    setTimer: (callback: () => void, ms: number) => {
      const handle = nextHandle++;
      timers.set(handle, { at: now + ms, callback });
      return handle;
    },
    clearTimer: (handle: unknown) => void timers.delete(handle as number),
    advance(ms: number) {
      now += ms;
      for (const [handle, timer] of [...timers]) {
        if (timer.at <= now) {
          timers.delete(handle);
          timer.callback();
        }
      }
    },
    pending: () => timers.size,
  };
}

/** A write that records its calls and resolves when the test says so. */
function fakeWrite(result: RunResult = { ok: true }) {
  const calls: { reason?: string; keepalive: boolean }[] = [];
  let release: () => void = () => undefined;
  const gate = new Promise<void>((resolve) => (release = resolve));
  return {
    calls,
    release: () => release(),
    run: async (extra: { reason?: string }, options: RunOptions) => {
      calls.push({ reason: extra.reason, keepalive: options.keepalive });
      await gate;
      return result;
    },
  };
}

const settle = () => new Promise((resolve) => setImmediate(resolve));

describe("PendingQueue", () => {
  it("writes nothing until the undo window has passed, then writes once", async () => {
    const clock = fakeClock();
    const queue = new PendingQueue<string>(5000, clock);
    const write = fakeWrite();
    const id = queue.schedule({ key: "decision:a", kind: "accept", meta: "Accepted", run: write.run });
    assert.equal(queue.entry("decision:a")?.state, "waiting");
    clock.advance(4999);
    assert.equal(write.calls.length, 0);
    clock.advance(1);
    assert.equal(write.calls.length, 1);
    assert.equal(queue.entry("decision:a")?.state, "saving");
    write.release();
    await settle();
    assert.equal(queue.entry("decision:a")?.state, "done");
    assert.equal(queue.entry("decision:a")?.settledAt, 6000);
    clock.advance(10_000);
    assert.equal(write.calls.length, 1);
    assert.equal(queue.pendingCount(), 0);
    queue.dismiss(id);
    assert.equal(queue.snapshot().length, 0);
  });

  it("undo drops the write so nothing is ever sent", () => {
    const clock = fakeClock();
    const queue = new PendingQueue<string>(5000, clock);
    const write = fakeWrite();
    const id = queue.schedule({ key: "decision:a", kind: "withdraw", meta: "", run: write.run });
    clock.advance(2000);
    assert.equal(queue.undo(id), true);
    assert.equal(queue.entry("decision:a")?.state, "undone");
    assert.equal(clock.pending(), 0);
    clock.advance(10_000);
    assert.equal(write.calls.length, 0);
    assert.equal(queue.undo(id), false);
  });

  it("cannot undo once the write has started", async () => {
    const clock = fakeClock();
    const queue = new PendingQueue<string>(5000, clock);
    const write = fakeWrite();
    const id = queue.schedule({ key: "k", kind: "accept", meta: "", run: write.run });
    void queue.flush(id);
    assert.equal(queue.undo(id), false);
    write.release();
    await settle();
    assert.equal(queue.entry("k")?.state, "done");
  });

  it("flushAll sends every waiting write at once with keepalive and waits for them", async () => {
    const clock = fakeClock();
    const queue = new PendingQueue<string>(5000, clock);
    const first = fakeWrite();
    const second = fakeWrite({ ok: false, error: "conflict", detail: "changed" });
    queue.schedule({ key: "a", kind: "accept", meta: "", run: first.run });
    const pausedId = queue.schedule({ key: "b", kind: "withdraw", meta: "", run: second.run });
    queue.pause(pausedId);
    queue.setExtra(pausedId, { reason: "Not needed" });

    let finished = false;
    const flushed = queue.flushAll({ keepalive: true }).then((count) => {
      finished = true;
      return count;
    });
    // Both requests are on their way before anything is awaited.
    assert.deepEqual(first.calls, [{ reason: undefined, keepalive: true }]);
    assert.deepEqual(second.calls, [{ reason: "Not needed", keepalive: true }]);
    await settle();
    assert.equal(finished, false);
    first.release();
    second.release();
    assert.equal(await flushed, 2);
    assert.equal(queue.entry("a")?.state, "done");
    assert.equal(queue.entry("b")?.state, "failed");
    assert.deepEqual(queue.entry("b")?.failure, { error: "conflict", detail: "changed" });
    // Nothing left to send; the timers were cleared.
    assert.equal(clock.pending(), 0);
    assert.equal(await queue.flushAll(), 0);
  });

  it("flushAll also waits for a write that is already running", async () => {
    const clock = fakeClock();
    const queue = new PendingQueue<string>(1000, clock);
    const write = fakeWrite();
    queue.schedule({ key: "a", kind: "accept", meta: "", run: write.run });
    clock.advance(1000);
    let finished = false;
    const flushed = queue.flushAll().then(() => (finished = true));
    await settle();
    assert.equal(finished, false);
    write.release();
    await flushed;
    assert.equal(write.calls.length, 1);
  });

  it("pausing keeps the time left and resuming continues from it", () => {
    const clock = fakeClock();
    const queue = new PendingQueue<string>(5000, clock);
    const write = fakeWrite();
    const id = queue.schedule({ key: "a", kind: "accept", meta: "", run: write.run });
    clock.advance(3000);
    queue.pause(id);
    clock.advance(60_000);
    assert.equal(write.calls.length, 0);
    queue.resume(id);
    clock.advance(1999);
    assert.equal(write.calls.length, 0);
    clock.advance(1);
    assert.equal(write.calls.length, 1);
  });

  it("a thrown or rejected write ends as failed, never stuck saving", async () => {
    const clock = fakeClock();
    const queue = new PendingQueue<string>(5000, clock);
    queue.schedule({
      key: "a",
      kind: "accept",
      meta: "",
      run: () => Promise.reject(new Error("offline")),
    });
    await queue.flushAll();
    assert.equal(queue.entry("a")?.state, "failed");
    assert.equal(queue.pendingCount(), 0);
  });

  it("a second action on the same key sends the first one right away", () => {
    const clock = fakeClock();
    const queue = new PendingQueue<string>(5000, clock);
    const first = fakeWrite();
    const second = fakeWrite();
    queue.schedule({ key: "a", kind: "accept", meta: "", run: first.run });
    queue.schedule({ key: "a", kind: "withdraw", meta: "", run: second.run });
    assert.equal(first.calls.length, 1);
    assert.equal(second.calls.length, 0);
    assert.equal(queue.entry("a")?.kind, "withdraw");
  });

  it("notifies subscribers with a new snapshot on every change", () => {
    const clock = fakeClock();
    const queue = new PendingQueue<string>(5000, clock);
    const seen: unknown[] = [];
    const stop = queue.subscribe(() => seen.push(queue.snapshot()));
    const id = queue.schedule({ key: "a", kind: "accept", meta: "", run: fakeWrite().run });
    queue.undo(id);
    stop();
    queue.dismiss(id);
    assert.equal(seen.length, 2);
    assert.notEqual(seen[0], seen[1]);
  });
});

describe("showsOutcome", () => {
  const base = {
    id: 1,
    key: "a",
    kind: "accept",
    meta: null,
    extra: {},
    deadline: null,
    remaining: 0,
    failure: null,
  };

  it("shows the new state while waiting and after success until the page reloads", () => {
    assert.equal(showsOutcome({ ...base, state: "waiting", settledAt: null }, 0), true);
    assert.equal(showsOutcome({ ...base, state: "saving", settledAt: null }, 0), true);
    assert.equal(showsOutcome({ ...base, state: "done", settledAt: 500 }, 400), true);
    assert.equal(showsOutcome({ ...base, state: "done", settledAt: 500 }, 600), false);
  });

  it("shows what was loaded after undo or a failure", () => {
    assert.equal(showsOutcome({ ...base, state: "undone", settledAt: 500 }, 0), false);
    assert.equal(showsOutcome({ ...base, state: "failed", settledAt: 500 }, 0), false);
    assert.equal(isActive({ ...base, state: "paused", settledAt: null }), true);
  });
});
