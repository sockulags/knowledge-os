import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { useNavigate } from "react-router";
import { Search } from "lucide-react";
import type { NavPayload, SearchPayload } from "../api/types";
import { api } from "../api/client";
import { iconFor } from "../lib/icons";
import { buildSections, type SwitchOption } from "../lib/quickSwitch";

/** Wait this long after the last keystroke before asking the full-text search. */
const TEXT_SEARCH_DELAY_MS = 150;

interface TextSearch {
  query: string;
  payload: SearchPayload;
}

/** The Ctrl K / Cmd K quick switcher. Titles of pages, projects, decisions,
 * skills, and repository documents are matched client-side over the nav's
 * record index as you type; the full-text search (/api/search) is asked
 * after a short pause, cancelling any request a newer keystroke made stale,
 * and adds the pages found only by a word in their text. Choosing a result
 * navigates through the router, so an editor with unsaved changes asks
 * first (useUnsavedChanges) and nothing typed there is lost.
 *
 * Accessibility: a modal dialog whose only focusable element is the search
 * field (an ARIA combobox); results are a listbox of grouped options
 * reached with aria-activedescendant, and focus cannot leave the dialog
 * while it is open. */
export function QuickFind({ open, onClose, nav }: { open: boolean; onClose: () => void; nav: NavPayload | null }) {
  const [query, setQuery] = useState("");
  const [text, setText] = useState<TextSearch | null>(null);
  const [activeIndex, setActiveIndex] = useState(0);
  const dialogRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const returnFocusRef = useRef<HTMLElement | null>(null);
  /** Set while closing, so the focus trap lets focus go back where it came from. */
  const closingRef = useRef(false);
  const navigate = useNavigate();
  const baseId = useId();
  const listboxId = `${baseId}-listbox`;
  const optionId = (index: number) => `${baseId}-option-${index}`;
  const language = nav?.language;

  // Reset on every open and remember where focus was, to give it back on close.
  useEffect(() => {
    if (!open) return;
    closingRef.current = false;
    returnFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setQuery("");
    setText(null);
    setActiveIndex(0);
    inputRef.current?.focus();
  }, [open]);

  // Full-text search, debounced; the cleanup aborts a request the next
  // keystroke has made stale.
  const trimmed = query.trim();
  useEffect(() => {
    if (!open || trimmed.length < 2) return;
    const controller = new AbortController();
    const handle = setTimeout(() => {
      api
        .search(`?q=${encodeURIComponent(trimmed)}`, controller.signal)
        .then((payload) => setText({ query: trimmed, payload }))
        .catch(() => {
          if (!controller.signal.aborted) setText(null);
        });
    }, TEXT_SEARCH_DELAY_MS);
    return () => {
      clearTimeout(handle);
      controller.abort();
    };
  }, [open, trimmed]);

  // Only ever show full-text results for exactly what is typed now.
  const currentText = text !== null && text.query === trimmed ? text.payload : null;
  const searching = trimmed.length >= 2 && currentText === null;

  const sections = useMemo(
    () =>
      trimmed
        ? buildSections(nav?.record_index ?? [], trimmed, currentText?.search_available ? currentText.results : null)
        : [],
    [nav, trimmed, currentText],
  );
  const options = useMemo(() => sections.flatMap((section) => section.options), [sections]);

  useEffect(() => setActiveIndex(0), [trimmed]);
  useEffect(() => {
    if (activeIndex >= options.length && options.length > 0) setActiveIndex(options.length - 1);
  }, [activeIndex, options.length]);

  useEffect(() => {
    if (!open || options.length === 0) return;
    document.getElementById(`${baseId}-option-${activeIndex}`)?.scrollIntoView({ block: "nearest" });
  }, [open, activeIndex, options.length, baseId]);

  // Focus trap: anything that takes focus outside the dialog hands it back.
  useEffect(() => {
    if (!open) return;
    function handleFocusIn(event: FocusEvent) {
      if (closingRef.current || !dialogRef.current) return;
      if (!dialogRef.current.contains(event.target as Node)) inputRef.current?.focus();
    }
    document.addEventListener("focusin", handleFocusIn);
    return () => document.removeEventListener("focusin", handleFocusIn);
  }, [open]);

  /** Close and give focus back to where it was (the editor, say). */
  function dismiss() {
    closingRef.current = true;
    const previous = returnFocusRef.current;
    if (previous?.isConnected) previous.focus();
    onClose();
  }

  /** Close, then navigate. If an editor has unsaved changes, its own
   * confirmation holds the navigation and focus is back in the editor. */
  function choose(option: SwitchOption | undefined) {
    if (!option) return;
    dismiss();
    navigate(option.href);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        if (options.length > 0) setActiveIndex((index) => (index + 1) % options.length);
        break;
      case "ArrowUp":
        event.preventDefault();
        if (options.length > 0) setActiveIndex((index) => (index - 1 + options.length) % options.length);
        break;
      case "Home":
      case "End":
        if (options.length > 0 && event.ctrlKey) {
          event.preventDefault();
          setActiveIndex(event.key === "Home" ? 0 : options.length - 1);
        }
        break;
      case "Enter":
        event.preventDefault();
        choose(options[activeIndex]);
        break;
      case "Escape":
        event.preventDefault();
        event.stopPropagation();
        dismiss();
        break;
      case "Tab":
        // The search field is the dialog's only stop; keep focus in it.
        event.preventDefault();
        break;
    }
  }

  if (!open) return null;

  let status: string | null = null;
  if (!trimmed) status = language?.quick_find_hint ?? null;
  else if (options.length === 0 && searching) status = language?.quick_find_searching ?? null;
  else if (options.length === 0) status = language?.quick_find_no_matches.replace("{query}", trimmed) ?? null;
  const textUnavailable = trimmed && currentText && !currentText.search_available ? currentText.disabled_reason : null;

  let flatIndex = 0;
  return (
    <div
      className="kos-scrim fixed inset-0 z-50 flex items-start justify-center pt-[12vh]"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) dismiss();
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label={language?.quick_find_label}
        className="kos-overlay mx-4 w-full max-w-xl overflow-hidden"
      >
        <div className="flex items-center gap-3 border-b border-(--color-border) px-4 py-3.5">
          <Search size={17} className="text-(--color-accent-text)" aria-hidden="true" />
          <input
            ref={inputRef}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={handleKeyDown}
            role="combobox"
            aria-label={language?.quick_find_label}
            aria-expanded={options.length > 0}
            aria-controls={listboxId}
            aria-autocomplete="list"
            aria-activedescendant={options.length > 0 ? optionId(activeIndex) : undefined}
            autoComplete="off"
            spellCheck={false}
            placeholder={language?.quick_find_placeholder}
            className="w-full bg-transparent text-[15px] outline-none placeholder:text-(--color-text-faint) focus-visible:outline-none"
          />
        </div>
        <div id={listboxId} role="listbox" aria-label={language?.quick_find_label} className="max-h-[60vh] overflow-y-auto px-1.5 py-1">
          {sections.map((section) => {
            const headingId = `${baseId}-group-${section.group}`;
            return (
              <div key={section.group} role="group" aria-labelledby={headingId} className="py-1">
                <div
                  id={headingId}
                  role="presentation"
                  className="kos-eyebrow px-2.5 pb-1 pt-2"
                >
                  {language?.quick_find_groups[section.group] ?? section.group}
                </div>
                {section.options.map((option) => {
                  const index = flatIndex++;
                  return (
                    <Option
                      key={option.key}
                      id={optionId(index)}
                      option={option}
                      active={index === activeIndex}
                      onHover={() => setActiveIndex(index)}
                      onChoose={() => choose(option)}
                    />
                  );
                })}
              </div>
            );
          })}
        </div>
        {(status || textUnavailable) && (
          <p role="status" className="border-t border-(--color-border) bg-(--color-bg-sidebar) px-4 py-2.5 text-xs text-(--color-text-faint)">
            {status ?? textUnavailable}
          </p>
        )}
      </div>
    </div>
  );
}

function Option({
  id,
  option,
  active,
  onHover,
  onChoose,
}: {
  id: string;
  option: SwitchOption;
  active: boolean;
  onHover: () => void;
  onChoose: () => void;
}) {
  const { entry } = option;
  const Icon = iconFor(entry.kind, entry.kind === "decision");
  return (
    <div
      id={id}
      role="option"
      aria-selected={active}
      // Keep focus in the search field; the click chooses.
      onMouseDown={(event) => event.preventDefault()}
      onMouseMove={() => {
        if (!active) onHover();
      }}
      onClick={onChoose}
      className={`flex cursor-pointer items-start gap-2.5 rounded-(--radius-control) px-2.5 py-2 text-sm ${
        active ? "bg-(--color-bg-active)" : ""
      }`}
    >
      <Icon
        size={14}
        className={`mt-0.5 shrink-0 ${active ? "text-(--color-accent-text)" : "text-(--color-text-faint)"}`}
        aria-hidden="true"
      />
      <span className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="truncate">{entry.title}</span>
        {option.snippetHtml && (
          <span
            className="truncate text-xs text-(--color-text-faint) [&_mark]:bg-transparent [&_mark]:font-semibold [&_mark]:text-(--color-text)"
            dangerouslySetInnerHTML={{ __html: option.snippetHtml }}
          />
        )}
      </span>
      <span
        className={`shrink-0 text-xs ${
          entry.status_pill?.tone === "amber" ? "text-(--color-accent-amber-text)" : "text-(--color-text-faint)"
        }`}
      >
        {entry.kind_label}
      </span>
    </div>
  );
}
