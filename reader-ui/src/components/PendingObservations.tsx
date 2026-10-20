import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router";
import { Bot, Check, ChevronRight, Copy, Eye, FolderKanban } from "lucide-react";
import { api } from "../api/client";
import type { DecisionLanguage, PendingObservation, PendingObservationsPayload, PropertyRow } from "../api/types";
import { observations, type ObservationReview } from "../api/write";
import { showsOutcome, type RunResult } from "../lib/pendingActions";
import { pendingActions, useOnPendingSettled, usePendingEntries, type DecisionEntry } from "../lib/pendingStore";
import { Callout } from "./Callout";
import { Markdown } from "./Markdown";

type ReviewAction = "retain" | "reject" | "promote";

/** The pending-queue key of an observation (see lib/pendingStore.ts). */
export const observationKey = (id: string) => `observation:${id}`;

// The queue's notice reads an outcome's notice; an observation has no Status row.
const NO_STATUS: PropertyRow = { label: "", value: null };

/** Retain, reject, or promote an observation in one step: the row goes at
 * once and the request waits out the undo window, like a decision action.
 * Undo drops it before anything reaches the core. */
export function startObservationReview(
  row: Pick<PendingObservation, "id" | "title">,
  action: ReviewAction,
  request: ObservationReview,
  labels: Record<string, string>,
  noticeLabels: DecisionLanguage["labels"],
): void {
  const notice = (labels[`notice_${action}`] ?? "").replace("{title}", row.title);
  pendingActions.schedule({
    key: observationKey(row.id),
    kind: action,
    meta: {
      recordId: observationKey(row.id),
      outcome: { notice, summary: notice, status: NO_STATUS },
      labels: noticeLabels,
      allowReason: false,
    },
    run: async (_extra, options): Promise<RunResult> => {
      const outcome = await observations.review(row.id, action, request, options);
      if (outcome.ok) return { ok: true };
      return { ok: false, error: outcome.failure.error, detail: outcome.failure.detail };
    },
  });
}

function ReviewActions({
  row,
  labels,
  noticeLabels,
}: {
  row: PendingObservation;
  labels: Record<string, string>;
  noticeLabels: DecisionLanguage["labels"];
}) {
  const [mode, setMode] = useState<"idle" | "reject" | "promote">("idle");
  const [reason, setReason] = useState("");
  const promote = row.actions.promote;
  const [title, setTitle] = useState(promote.title);
  const [targetId, setTargetId] = useState(promote.target_id);
  const [general, setGeneral] = useState(false);
  const [acknowledged, setAcknowledged] = useState(false);

  const start = (action: ReviewAction, request: Omit<ObservationReview, "expected_sha256">) =>
    startObservationReview(row, action, { expected_sha256: row.content_sha256, ...request }, labels, noticeLabels);

  if (mode === "reject") {
    const ready = reason.trim() !== "";
    return (
      <form
        className="space-y-2"
        onSubmit={(event) => {
          event.preventDefault();
          if (ready) start("reject", { reason: reason.trim() });
        }}
      >
        <label className="block text-[13px] text-(--color-text-muted)">
          {labels.reason_label}
          <input
            className="kos-input mt-1 block w-full px-2 py-1 text-sm"
            required
            autoFocus
            placeholder={labels.reason_placeholder}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
          />
        </label>
        <div className="flex gap-2">
          <button type="submit" className="kos-btn kos-btn-primary kos-btn-sm" disabled={!ready}>
            {labels.confirm_reject}
          </button>
          <button type="button" className="kos-btn kos-btn-ghost kos-btn-sm" onClick={() => setMode("idle")}>
            {labels.cancel}
          </button>
        </div>
      </form>
    );
  }

  if (mode === "promote") {
    const ready = title.trim() !== "" && targetId.trim() !== "" && (!promote.acknowledge_related || acknowledged);
    return (
      <form
        className="space-y-2"
        onSubmit={(event) => {
          event.preventDefault();
          if (!ready) return;
          start("promote", {
            target_id: targetId.trim(),
            title: title.trim(),
            scope: general ? "general" : row.scope,
            acknowledge_related: promote.acknowledge_related && acknowledged,
            allow_scope_broadening: promote.allow_scope_broadening && general,
          });
        }}
      >
        <label className="block text-[13px] text-(--color-text-muted)">
          {labels.promote_title}
          <input
            className="kos-input mt-1 block w-full px-2 py-1 text-sm"
            required
            autoFocus
            value={title}
            onChange={(event) => setTitle(event.target.value)}
          />
        </label>
        <label className="block text-[13px] text-(--color-text-muted)">
          {labels.promote_id}
          <input
            className="kos-input mt-1 block w-full px-2 py-1 font-mono text-sm"
            required
            value={targetId}
            onChange={(event) => setTargetId(event.target.value)}
          />
        </label>
        {promote.allow_scope_broadening && (
          <label className="flex items-center gap-2 text-[13px] text-(--color-text-muted)">
            <input type="checkbox" checked={general} onChange={(event) => setGeneral(event.target.checked)} />
            {(labels.promote_general ?? "").replace("{project}", row.project.title)}
          </label>
        )}
        {promote.acknowledge_related && (
          <label className="flex items-center gap-2 text-[13px] text-(--color-text-muted)">
            <input type="checkbox" checked={acknowledged} onChange={(event) => setAcknowledged(event.target.checked)} />
            {labels.acknowledge_related}
          </label>
        )}
        <div className="flex gap-2">
          <button type="submit" className="kos-btn kos-btn-primary kos-btn-sm" disabled={!ready}>
            {labels.confirm_promote}
          </button>
          <button type="button" className="kos-btn kos-btn-ghost kos-btn-sm" onClick={() => setMode("idle")}>
            {labels.cancel}
          </button>
        </div>
      </form>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      {row.actions.retain && (
        <button type="button" className="kos-btn kos-btn-secondary kos-btn-sm" onClick={() => start("retain", {})}>
          {labels.act_retain}
        </button>
      )}
      <button type="button" className="kos-btn kos-btn-secondary kos-btn-sm" onClick={() => setMode("reject")}>
        {labels.act_reject}
      </button>
      <button type="button" className="kos-btn kos-btn-secondary kos-btn-sm" onClick={() => setMode("promote")}>
        {labels.act_promote}
      </button>
    </div>
  );
}

/** Copies text, through a hidden text area where the clipboard API is missing
 * (an insecure context or an older browser). Resolves false when both fail. */
export async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // fall through to the text area
  }
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.appendChild(area);
  area.select();
  try {
    return document.execCommand("copy");
  } catch {
    return false;
  } finally {
    area.remove();
  }
}

function CopyLine({ text, labels }: { text: string; labels: Record<string, string> }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="flex items-start gap-2">
      <code className="min-w-0 flex-1 break-all rounded-[5px] bg-(--color-bg-sidebar) px-2 py-1 font-mono text-xs text-(--color-text)">
        {text}
      </code>
      <button
        type="button"
        className="inline-flex shrink-0 items-center gap-1 rounded-[5px] px-1.5 py-1 text-xs text-(--color-text-muted) hover:bg-(--color-bg-hover) hover:text-(--color-text)"
        onClick={() => {
          void copyText(text).then((ok) => {
            if (!ok) return;
            setCopied(true);
            window.setTimeout(() => setCopied(false), 1500);
          });
        }}
      >
        {copied ? <Check size={12} /> : <Copy size={12} />}
        {copied ? labels.copied : labels.copy}
      </button>
    </div>
  );
}

function ObservationRow({
  row,
  labels,
  noticeLabels,
  failed,
}: {
  row: PendingObservation;
  labels: Record<string, string>;
  noticeLabels: DecisionLanguage["labels"];
  failed: DecisionEntry | null;
}) {
  const [open, setOpen] = useState(false);
  return (
    <li className="kos-card px-5 py-4" data-testid="observation-row">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-(--color-text-faint)">
        <span className="flex items-center gap-1 font-medium text-(--color-accent-yellow-text)">
          <Eye size={12} />
          {row.trust}
        </span>
        <span className="flex items-center gap-1">
          <FolderKanban size={12} />
          {row.project.title}
        </span>
        <span className="flex items-center gap-1" title={row.proposed_exact ?? undefined}>
          <Bot size={12} />
          {row.proposed_by.label}
          {row.proposed_display && <> · {row.proposed_display}</>}
        </span>
      </div>
      <Link
        to={`/r/${row.id}`}
        className="mt-1.5 block rounded-sm font-serif text-[18px] font-semibold leading-snug hover:underline hover:decoration-1 hover:underline-offset-[3px]"
      >
        {row.title}
      </Link>
      {row.excerpt && <p className="mt-1 line-clamp-2 text-sm text-(--color-text-muted)">{row.excerpt}</p>}

      {row.related !== null && (
        <div className="mt-3 text-sm">
          {row.related.length === 0 ? (
            <p className="text-(--color-text-faint)">{labels.no_related}</p>
          ) : (
            <>
              <h3 className="text-[13px] font-medium text-(--color-text-muted)">{labels.related}</h3>
              <ul className="mt-1 space-y-0.5" aria-label={labels.related}>
                {row.related.map((item) => (
                  <li key={item.id}>
                    {item.exists ? (
                      <Link to={`/r/${item.id}`} className="text-(--color-accent-text) underline decoration-1 underline-offset-[3px]">
                        {item.title}
                      </Link>
                    ) : (
                      item.title
                    )}
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}

      {row.packet_html !== null && (
        <div className="mt-3 text-xs">
          <button
            type="button"
            onClick={() => setOpen((value) => !value)}
            aria-expanded={open}
            className="flex items-center gap-1 text-(--color-text-faint) hover:text-(--color-text)"
          >
            <ChevronRight size={12} className={open ? "rotate-90 transition-transform duration-100" : "transition-transform duration-100"} />
            {labels.packet}
          </button>
          {open && (
            <div className="mt-2 rounded-[5px] border border-(--color-border) px-3 py-2" data-testid="observation-packet">
              <Markdown html={row.packet_html} className="text-sm" />
            </div>
          )}
        </div>
      )}

      <div className="mt-4 space-y-3 border-t border-(--color-border) pt-3.5" data-testid="observation-actions">
        {failed?.failure && (
          <Callout tone="danger">
            <p>{(labels.failed ?? "").replace("{title}", row.title)}</p>
            <p className="mt-1 whitespace-pre-wrap break-words">{failed.failure.detail}</p>
          </Callout>
        )}
        <ReviewActions key={failed?.id ?? 0} row={row} labels={labels} noticeLabels={noticeLabels} />
      </div>

      <div className="mt-4 space-y-2 border-t border-(--color-border) pt-3.5 text-xs">
        <p className="text-(--color-text-muted)">{labels.agent}</p>
        <CopyLine text={row.agent_phrase} labels={labels} />
        <p className="pt-1 text-(--color-text-muted)">{labels.commands}</p>
        <ul className="space-y-1.5">
          {row.commands.map((item) => (
            <li key={item.action}>
              <p className="mb-0.5 text-(--color-text-faint)">{item.label}</p>
              <CopyLine text={item.command} labels={labels} />
            </li>
          ))}
        </ul>
      </div>
    </li>
  );
}

/**
 * Observations agents left that nobody has reviewed yet, each with its review
 * packet, Keep / Dismiss / Turn into a page, and the command or agent request
 * that does the same. A review leaves the list at once and is sent after the
 * undo window; a refusal brings the row back with the reason. Loads on its
 * own so the rest of Decide never waits on it, and shows nothing while
 * loading, on a failed read, or when nothing waits. `onCount` hears how many
 * observations still wait on screen.
 */
export function PendingObservations({ onCount }: { onCount?: (count: number) => void }) {
  const [loaded, setLoaded] = useState<{ payload: PendingObservationsPayload; loadedAt: number } | null>(null);
  const [generation, setGeneration] = useState(0);
  const entries = usePendingEntries();
  const reload = useCallback(() => setGeneration((value) => value + 1), []);
  useOnPendingSettled(reload);
  useEffect(() => {
    let current = true;
    const loadedAt = Date.now();
    api.pendingObservations().then(
      (payload) => current && setLoaded({ payload, loadedAt }),
      () => undefined,
    );
    return () => {
      current = false;
    };
  }, [generation]);

  const acted = new Set(
    loaded === null
      ? []
      : entries.filter((entry) => showsOutcome(entry, loaded.loadedAt)).map((entry) => entry.meta.recordId),
  );
  const rows = loaded === null ? [] : loaded.payload.items.filter((row) => !acted.has(observationKey(row.id)));
  const waiting = loaded === null ? 0 : Math.max(loaded.payload.count - (loaded.payload.items.length - rows.length), 0);
  useEffect(() => onCount?.(waiting), [onCount, waiting]);

  if (loaded === null || waiting === 0) return null;
  const payload = loaded.payload;
  const failures = new Map(
    entries
      .filter((entry) => entry.state === "failed" && entry.key.startsWith("observation:"))
      .map((entry) => [entry.meta.recordId, entry]),
  );
  return (
    <section className="mt-8" aria-label={payload.heading} data-testid="pending-observations">
      <h2 className="kos-heading">{payload.heading}</h2>
      <p className="mt-1 text-sm text-(--color-text-muted)">{payload.intro}</p>
      {payload.count_label && <p className="mt-1 text-sm text-(--color-text-faint)">{payload.count_label}</p>}
      {payload.error && (
        <div className="mt-3">
          <Callout tone="neutral">{payload.error}</Callout>
        </div>
      )}
      <ul className="mt-4 space-y-3">
        {rows.map((row) => (
          <ObservationRow
            key={row.id}
            row={row}
            labels={payload.labels}
            noticeLabels={payload.notice_labels}
            failed={failures.get(observationKey(row.id)) ?? null}
          />
        ))}
      </ul>
    </section>
  );
}
