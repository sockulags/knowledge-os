import { useId, useMemo, useState, type KeyboardEvent } from "react";
import { X } from "lucide-react";
import type { RecordIndexEntry } from "../api/types";
import { normalize, rankTitles } from "../lib/quickSwitch";
import { fieldLabelClass, inputClass } from "./EditorParts";

/** Rows shown under the search field. */
const OPTION_LIMIT = 8;
const ID_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

/** The pages a relation can point at: every record in the quick-find index
 * (skills and repository docs are not records), once per id. */
export function linkablePages(index: RecordIndexEntry[]): Map<string, RecordIndexEntry> {
  const pages = new Map<string, RecordIndexEntry>();
  for (const entry of index) {
    if (entry.kind !== "skill" && entry.kind !== "doc" && !pages.has(entry.id)) pages.set(entry.id, entry);
  }
  return pages;
}

/** The ids in `ids` that no known page has. Nothing is flagged while the
 * page list is still loading (`pages` null); the server checks on Save. */
export function unknownIds(ids: string[], pages: Map<string, RecordIndexEntry> | null): string[] {
  return pages === null ? [] : ids.filter((id) => !pages.has(id));
}

type Option = { kind: "page"; entry: RecordIndexEntry } | { kind: "id"; id: string };

function optionsFor(query: string, pages: Map<string, RecordIndexEntry> | null, taken: Set<string>): Option[] {
  const q = query.trim();
  if (!q) return [];
  const free = [...(pages?.values() ?? [])].filter((entry) => !taken.has(entry.id));
  const byTitle = rankTitles(free, q).map((item) => item.entry);
  const needle = normalize(q);
  const byId = free.filter((entry) => entry.id.includes(needle) && !byTitle.includes(entry));
  const options: Option[] = [...byTitle, ...byId].slice(0, OPTION_LIMIT).map((entry) => ({ kind: "page", entry }));
  // A typed id no known page has can still be added; it shows as an error.
  if (ID_PATTERN.test(q) && !pages?.has(q) && !taken.has(q)) options.push({ kind: "id", id: q });
  return options;
}

/**
 * A list of page ids, edited by searching page titles: chosen pages show as
 * removable chips, and an id no known page has is marked as an error at once
 * rather than only when Save is refused.
 */
export function PagePicker({
  label,
  hint,
  value,
  onChange,
  pages,
  selfId,
}: {
  label: string;
  hint?: string;
  value: string[];
  onChange: (ids: string[]) => void;
  /** Known pages by id, or null while they load. */
  pages: Map<string, RecordIndexEntry> | null;
  /** The page being edited; it is not offered as its own relation. */
  selfId?: string;
}) {
  const baseId = useId();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const [open, setOpen] = useState(false);
  const taken = useMemo(() => new Set([...value, ...(selfId ? [selfId] : [])]), [value, selfId]);
  const options = useMemo(() => optionsFor(query, pages, taken), [query, pages, taken]);
  const unknown = unknownIds(value, pages);
  const listId = `${baseId}-options`;
  const errorId = `${baseId}-error`;
  const shown = open && options.length > 0;

  function choose(option: Option) {
    onChange([...value, option.kind === "page" ? option.entry.id : option.id]);
    setQuery("");
    setActive(0);
  }

  function handleKey(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown" && options.length > 0) {
      event.preventDefault();
      setOpen(true);
      setActive((index) => (index + 1) % options.length);
    } else if (event.key === "ArrowUp" && options.length > 0) {
      event.preventDefault();
      setActive((index) => (index - 1 + options.length) % options.length);
    } else if (event.key === "Enter" && shown) {
      event.preventDefault();
      choose(options[Math.min(active, options.length - 1)]);
    } else if (event.key === "Escape" && shown) {
      event.preventDefault();
      setOpen(false);
    } else if (event.key === "Backspace" && query === "" && value.length > 0) {
      onChange(value.slice(0, -1));
    }
  }

  return (
    <div role="group" aria-labelledby={`${baseId}-label`}>
      <span id={`${baseId}-label`} className={fieldLabelClass}>
        {label}
      </span>
      {value.length > 0 && (
        <ul className="mb-1.5 flex flex-wrap gap-1.5">
          {value.map((id) => {
            const entry = pages?.get(id);
            const missing = unknown.includes(id);
            const name = entry?.title ?? id;
            return (
              <li
                key={id}
                className={`flex max-w-full items-center gap-1 rounded-[5px] border px-2 py-0.5 text-[13px] ${
                  missing
                    ? "border-(--color-danger) text-(--color-danger)"
                    : "border-(--color-border-strong) text-(--color-text)"
                }`}
                title={id}
              >
                <span className="truncate">{name}</span>
                <button
                  type="button"
                  onClick={() => onChange(value.filter((item) => item !== id))}
                  className="flex h-4 w-4 shrink-0 items-center justify-center rounded-[3px] text-(--color-text-faint) hover:bg-(--color-bg-hover) hover:text-(--color-text)"
                  aria-label={`Remove ${name}`}
                >
                  <X size={12} />
                </button>
              </li>
            );
          })}
        </ul>
      )}
      <div className="relative">
        <input
          className={inputClass}
          role="combobox"
          aria-label={`Add to ${label.toLowerCase()}`}
          aria-expanded={shown}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={shown ? `${baseId}-option-${active}` : undefined}
          aria-invalid={unknown.length > 0}
          aria-describedby={unknown.length > 0 ? errorId : undefined}
          placeholder="Search page titles"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setActive(0);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => setOpen(false)}
          onKeyDown={handleKey}
        />
        {shown && (
          <ul
            id={listId}
            role="listbox"
            aria-label={label}
            className="absolute inset-x-0 top-full z-30 mt-1 max-h-72 overflow-y-auto rounded-(--radius-control) border border-(--color-border-strong) bg-(--color-bg-raised) py-1 shadow-lg"
          >
            {options.map((option, index) => (
              <li
                key={option.kind === "page" ? option.entry.id : `id:${option.id}`}
                id={`${baseId}-option-${index}`}
                role="option"
                aria-selected={index === active}
                // Chosen on mousedown, before the field's blur closes the list.
                onMouseDown={(event) => {
                  event.preventDefault();
                  choose(option);
                }}
                onMouseEnter={() => setActive(index)}
                className={`cursor-pointer px-3 py-1.5 text-sm ${index === active ? "bg-(--color-bg-active)" : ""}`}
              >
                {option.kind === "page" ? (
                  <>
                    <span className="block truncate text-(--color-text)">{option.entry.title}</span>
                    <span className="block truncate text-xs text-(--color-text-faint)">
                      {option.entry.kind_label} · {option.entry.id}
                    </span>
                  </>
                ) : (
                  <span className="text-(--color-text-muted)">Use the id “{option.id}”</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
      {unknown.length > 0 ? (
        <span id={errorId} className="mt-1.5 block text-xs text-(--color-danger)" role="alert">
          {unknown.length === 1
            ? `No page has the id “${unknown[0]}”. Remove it or pick a page.`
            : `No page has the ids ${unknown.map((id) => `“${id}”`).join(", ")}. Remove them or pick pages.`}
        </span>
      ) : (
        hint && <span className="mt-1.5 block text-xs text-(--color-text-faint)">{hint}</span>
      )}
    </div>
  );
}
