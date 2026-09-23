import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { Search } from "lucide-react";
import type { NavPayload, RecordIndexEntry, SearchResult } from "../api/types";
import { api } from "../api/client";
import { iconFor } from "../lib/icons";
import { Pill } from "./Pill";

function hrefFor(kind: string, id: string): string {
  if (kind === "skill") return `/s/${id}`;
  if (kind === "doc") return `/f/${id}`;
  return `/r/${id}`;
}

/** Ctrl K / Cmd K command palette. Title matching runs client-side over the
 * nav's record index (works with no search index built); when a full-text
 * index is available, matching results from /api/search appear under
 * their own heading, debounced so typing stays snappy. */
export function QuickFind({ open, onClose, nav }: { open: boolean; onClose: () => void; nav: NavPayload | null }) {
  const [query, setQuery] = useState("");
  const [fullText, setFullText] = useState<SearchResult[]>([]);
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (open) {
      setQuery("");
      setFullText([]);
      setActiveIndex(0);
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  const titleMatches = useMemo<RecordIndexEntry[]>(() => {
    const trimmed = query.trim().toLowerCase();
    if (!trimmed || !nav) return [];
    return nav.record_index.filter((entry) => entry.title.toLowerCase().includes(trimmed)).slice(0, 8);
  }, [query, nav]);

  useEffect(() => {
    const trimmed = query.trim();
    if (!trimmed) {
      setFullText([]);
      return;
    }
    const handle = setTimeout(() => {
      api
        .search(`?q=${encodeURIComponent(trimmed)}`)
        .then((data) => setFullText(data.search_available ? data.results.slice(0, 6) : []))
        .catch(() => setFullText([]));
    }, 150);
    return () => clearTimeout(handle);
  }, [query]);

  const combined = useMemo(() => {
    const titleIds = new Set(titleMatches.map((entry) => entry.id));
    const extraFullText = fullText.filter((result) => !titleIds.has(result.id));
    return [
      ...titleMatches.map((entry) => ({ kind: "title" as const, entry })),
      ...extraFullText.map((result) => ({ kind: "fulltext" as const, result })),
    ];
  }, [titleMatches, fullText]);

  useEffect(() => setActiveIndex(0), [query]);

  useEffect(() => {
    if (!open) return;
    function handleKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onClose();
      } else if (event.key === "ArrowDown") {
        event.preventDefault();
        setActiveIndex((index) => Math.min(index + 1, combined.length - 1));
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        setActiveIndex((index) => Math.max(index - 1, 0));
      } else if (event.key === "Enter") {
        event.preventDefault();
        const item = combined[activeIndex];
        if (!item) return;
        const href = item.kind === "title" ? hrefFor(item.entry.kind, item.entry.id) : `/r/${item.result.id}`;
        navigate(href);
        onClose();
      }
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [open, combined, activeIndex, navigate, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/30 pt-[12vh]" onClick={onClose}>
      <div
        className="mx-4 w-full max-w-lg overflow-hidden rounded-xl border border-(--color-border) bg-(--color-bg-raised) shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center gap-2.5 border-b border-(--color-border) px-4 py-3">
          <Search size={16} className="text-(--color-text-faint)" />
          <input
            ref={inputRef}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={nav?.language.quick_find_placeholder ?? "Jump to a page, skill, or document…"}
            className="w-full bg-transparent text-sm outline-none placeholder:text-(--color-text-faint)"
          />
        </div>
        <div className="max-h-[60vh] overflow-y-auto py-2">
          {combined.length === 0 && (
            <p className="px-4 py-6 text-center text-sm text-(--color-text-faint)">
              {query.trim() ? "No matches." : "Start typing to search."}
            </p>
          )}
          {titleMatches.length > 0 && (
            <p className="px-4 pb-1 pt-1 text-xs font-semibold uppercase tracking-wide text-(--color-text-faint)">
              Titles
            </p>
          )}
          {titleMatches.map((entry, index) => {
            const active = index === activeIndex;
            const Icon = iconFor(entry.kind, entry.kind === "decision");
            return (
              <button
                key={`t-${entry.id}`}
                type="button"
                onMouseEnter={() => setActiveIndex(index)}
                onClick={() => {
                  navigate(hrefFor(entry.kind, entry.id));
                  onClose();
                }}
                className={`flex w-full items-center gap-2.5 px-4 py-2 text-left text-sm ${active ? "bg-(--color-bg-hover)" : ""}`}
              >
                <Icon size={14} className="shrink-0 opacity-70" />
                <span className="min-w-0 flex-1 truncate">{entry.title}</span>
                <Pill pill={entry.status_pill} />
              </button>
            );
          })}
          {combined.length > titleMatches.length && (
            <p className="px-4 pb-1 pt-3 text-xs font-semibold uppercase tracking-wide text-(--color-text-faint)">
              Full text
            </p>
          )}
          {combined.slice(titleMatches.length).map((item, offset) => {
            if (item.kind !== "fulltext") return null;
            const index = titleMatches.length + offset;
            const active = index === activeIndex;
            return (
              <button
                key={`f-${item.result.id}`}
                type="button"
                onMouseEnter={() => setActiveIndex(index)}
                onClick={() => {
                  navigate(`/r/${item.result.id}`);
                  onClose();
                }}
                className={`flex w-full flex-col gap-0.5 px-4 py-2 text-left text-sm ${active ? "bg-(--color-bg-hover)" : ""}`}
              >
                <span className="truncate font-medium">{item.result.title}</span>
                <span
                  className="truncate text-xs text-(--color-text-faint) [&_mark]:bg-transparent [&_mark]:font-semibold [&_mark]:text-(--color-text)"
                  dangerouslySetInnerHTML={{ __html: item.result.snippet_html }}
                />
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
