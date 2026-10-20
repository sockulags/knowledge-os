import { useEffect, useState } from "react";
import { Link } from "react-router";
import { Bot, Check, ChevronRight, Copy, Eye, FolderKanban } from "lucide-react";
import { api } from "../api/client";
import type { PendingObservation, PendingObservationsPayload } from "../api/types";
import { Callout } from "./Callout";
import { Markdown } from "./Markdown";

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

function ObservationRow({ row, labels }: { row: PendingObservation; labels: Record<string, string> }) {
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
 * packet and the command or agent request that reviews it. Read-only: the app
 * cannot retain, reject, or promote yet. Loads on its own so the rest of
 * Decide never waits on it, and shows nothing while loading, on a failed
 * read, or when nothing waits.
 */
export function PendingObservations() {
  const [payload, setPayload] = useState<PendingObservationsPayload | null>(null);
  useEffect(() => {
    let current = true;
    api.pendingObservations().then(
      (value) => current && setPayload(value),
      () => undefined,
    );
    return () => {
      current = false;
    };
  }, []);

  if (payload === null || payload.count === 0) return null;
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
        {payload.items.map((row) => (
          <ObservationRow key={row.id} row={row} labels={payload.labels} />
        ))}
      </ul>
    </section>
  );
}
