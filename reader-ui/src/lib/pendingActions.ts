// One-click actions with Undo (issue #78).
//
// Accepting, withdrawing, and accepting a replacement run in one click. The
// interface shows the new state at once, and the write (and so its Git
// commit) waits here for a few seconds so the notice can offer Undo. Undo
// drops the waiting write: nothing reaches the core, so nothing is written
// or committed and no reverse operation is needed.
//
// A waiting write is never dropped by leaving: `flushAll` sends everything
// that still waits right away. The shell calls it when the route changes,
// when the page is hidden or closed (with `keepalive`, so the request
// survives the page), and before any structure change; the desktop app
// calls `window.kosFlushPendingActions` and waits for it before it stops
// the core (switching knowledge base, closing the window, quitting).
//
// This module is plain TypeScript with no React or DOM dependency, so it
// runs under `npm test`; timers and the clock are injected.

export type PendingState = "waiting" | "paused" | "saving" | "done" | "failed" | "undone";

/** What a write sends besides its fixed arguments: an optional reason. */
export interface PendingExtra {
  reason?: string;
}

export interface RunOptions {
  /** Send with `fetch(..., {keepalive: true})`: the page is going away. */
  keepalive: boolean;
}

export type RunResult = { ok: true } | { ok: false; detail: string; error: string };

export interface PendingRequest<M> {
  /** One action per key; a second action on the same key flushes the first. */
  key: string;
  kind: string;
  /** Whatever the interface needs to show it (the notice text, labels). */
  meta: M;
  run: (extra: PendingExtra, options: RunOptions) => Promise<RunResult>;
}

export interface PendingEntry<M> {
  id: number;
  key: string;
  kind: string;
  meta: M;
  state: PendingState;
  extra: PendingExtra;
  /** When a waiting entry runs, on the injected clock; null while paused or after. */
  deadline: number | null;
  /** Time left when it was paused. */
  remaining: number;
  /** When it finished (done, failed, or undone). */
  settledAt: number | null;
  failure: { error: string; detail: string } | null;
}

export interface Clock {
  now: () => number;
  setTimer: (callback: () => void, ms: number) => unknown;
  clearTimer: (handle: unknown) => void;
}

const ACTIVE: ReadonlySet<PendingState> = new Set(["waiting", "paused", "saving"]);

/** True while the entry's write has not finished: the interface shows its outcome. */
export function isActive(entry: PendingEntry<unknown>): boolean {
  return ACTIVE.has(entry.state);
}

/** Whether a page whose data was loaded at `loadedAt` should still show the
 * entry's outcome instead of what it loaded: while the write waits or runs,
 * and after it succeeded until the page has reloaded. */
export function showsOutcome(entry: PendingEntry<unknown>, loadedAt: number): boolean {
  if (isActive(entry)) return true;
  return entry.state === "done" && entry.settledAt !== null && entry.settledAt > loadedAt;
}

export class PendingQueue<M> {
  readonly delayMs: number;
  private readonly clock: Clock;
  private entries: PendingEntry<M>[] = [];
  private readonly runs = new Map<number, PendingRequest<M>["run"]>();
  private readonly timers = new Map<number, unknown>();
  private readonly running = new Map<number, Promise<void>>();
  private readonly listeners = new Set<() => void>();
  private nextId = 1;

  constructor(delayMs: number, clock: Clock) {
    this.delayMs = delayMs;
    this.clock = clock;
  }

  /** The current entries, newest last. A new array after every change. */
  snapshot = (): readonly PendingEntry<M>[] => this.entries;

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  /** The newest entry for `key`, in any state. */
  entry(key: string): PendingEntry<M> | null {
    for (let index = this.entries.length - 1; index >= 0; index--) {
      if (this.entries[index].key === key) return this.entries[index];
    }
    return null;
  }

  /** How many writes still wait or run. */
  pendingCount(): number {
    return this.entries.filter(isActive).length;
  }

  schedule(request: PendingRequest<M>): number {
    const earlier = this.entry(request.key);
    if (earlier !== null && (earlier.state === "waiting" || earlier.state === "paused")) {
      void this.flush(earlier.id, { keepalive: false });
    }
    const id = this.nextId++;
    const entry: PendingEntry<M> = {
      id,
      key: request.key,
      kind: request.kind,
      meta: request.meta,
      state: "waiting",
      extra: {},
      deadline: this.clock.now() + this.delayMs,
      remaining: this.delayMs,
      settledAt: null,
      failure: null,
    };
    this.runs.set(id, request.run);
    this.entries = [...this.entries.filter((item) => item.key !== request.key || isActive(item)), entry];
    this.arm(id, this.delayMs);
    this.emit();
    return id;
  }

  /** Drop a write that has not started. Returns false once it is running or finished. */
  undo(id: number): boolean {
    const entry = this.find(id);
    if (entry === null || (entry.state !== "waiting" && entry.state !== "paused")) return false;
    this.disarm(id);
    this.runs.delete(id);
    this.update(id, { state: "undone", deadline: null, settledAt: this.clock.now() });
    return true;
  }

  /** Stop the countdown, e.g. while the pointer is over the notice or a reason is typed. */
  pause(id: number): void {
    const entry = this.find(id);
    if (entry === null || entry.state !== "waiting") return;
    this.disarm(id);
    const remaining = Math.max((entry.deadline ?? this.clock.now()) - this.clock.now(), 0);
    this.update(id, { state: "paused", deadline: null, remaining });
  }

  /** Continue a paused countdown with the time it had left (at least a second). */
  resume(id: number): void {
    const entry = this.find(id);
    if (entry === null || entry.state !== "paused") return;
    const remaining = Math.max(entry.remaining, 1000);
    this.update(id, { state: "waiting", deadline: this.clock.now() + remaining, remaining });
    this.arm(id, remaining);
  }

  setExtra(id: number, extra: PendingExtra): void {
    const entry = this.find(id);
    if (entry === null || !isActive(entry) || entry.state === "saving") return;
    this.update(id, { extra: { ...entry.extra, ...extra } });
  }

  /** Remove a finished entry (its notice was dismissed). */
  dismiss(id: number): void {
    const entry = this.find(id);
    if (entry === null || isActive(entry)) return;
    this.entries = this.entries.filter((item) => item.id !== id);
    this.emit();
  }

  /** Run one waiting entry now; resolves when its write has finished. */
  flush(id: number, options: RunOptions = { keepalive: false }): Promise<void> {
    const running = this.running.get(id);
    if (running !== undefined) return running;
    const entry = this.find(id);
    const run = this.runs.get(id);
    if (entry === null || run === undefined || (entry.state !== "waiting" && entry.state !== "paused")) {
      return Promise.resolve();
    }
    this.disarm(id);
    this.update(id, { state: "saving", deadline: null });
    let result: Promise<RunResult>;
    try {
      result = run(entry.extra, options);
    } catch (error) {
      result = Promise.resolve({ ok: false, error: "unavailable", detail: String(error) });
    }
    const done = result
      .catch((error: unknown): RunResult => ({ ok: false, error: "unavailable", detail: String(error) }))
      .then((outcome) => {
        this.running.delete(id);
        this.runs.delete(id);
        if (outcome.ok) this.update(id, { state: "done", settledAt: this.clock.now() });
        else
          this.update(id, {
            state: "failed",
            settledAt: this.clock.now(),
            failure: { error: outcome.error, detail: outcome.detail },
          });
      });
    this.running.set(id, done);
    return done;
  }

  /** Send every write that still waits, at once, and wait for all of them
   * (and for any already running). Resolves with how many it sent. */
  async flushAll(options: RunOptions = { keepalive: false }): Promise<number> {
    const waiting = this.entries.filter((item) => item.state === "waiting" || item.state === "paused");
    // Start every request before awaiting any, so all of them are on their
    // way even when the page is about to go.
    const all = [...waiting.map((item) => this.flush(item.id, options)), ...this.running.values()];
    await Promise.all(all);
    return waiting.length;
  }

  private find(id: number): PendingEntry<M> | null {
    return this.entries.find((item) => item.id === id) ?? null;
  }

  private update(id: number, change: Partial<PendingEntry<M>>): void {
    this.entries = this.entries.map((item) => (item.id === id ? { ...item, ...change } : item));
    this.emit();
  }

  private arm(id: number, ms: number): void {
    this.timers.set(
      id,
      this.clock.setTimer(() => {
        this.timers.delete(id);
        void this.flush(id);
      }, ms),
    );
  }

  private disarm(id: number): void {
    const handle = this.timers.get(id);
    if (handle !== undefined) this.clock.clearTimer(handle);
    this.timers.delete(id);
  }

  private emit(): void {
    for (const listener of [...this.listeners]) listener();
  }
}

/** How long a one-click action waits for Undo before it is written. */
export const UNDO_WINDOW_MS = 6000;
