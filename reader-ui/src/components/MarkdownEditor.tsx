import { useState } from "react";
import { write } from "../api/write";
import { Markdown } from "./Markdown";

/** A plain Markdown textarea with a Write / Preview toggle. The preview is
 * rendered by the core (POST /api/preview), so it matches the record page. */
export function MarkdownEditor({
  value,
  onChange,
  path,
}: {
  value: string;
  onChange: (value: string) => void;
  /** The record's path, so relative links in the preview resolve like on the page. */
  path?: string;
}) {
  const [mode, setMode] = useState<"write" | "preview">("write");
  const [preview, setPreview] = useState<{ html: string } | { error: string } | null>(null);

  async function showPreview() {
    setMode("preview");
    setPreview(null);
    const outcome = await write.preview(value, path);
    setPreview(outcome.ok ? { html: outcome.data.html } : { error: outcome.failure.detail });
  }

  const tabClass = (active: boolean) =>
    `rounded-md px-2.5 py-1 text-sm ${
      active ? "bg-(--color-bg-hover) font-medium" : "text-(--color-text-muted) hover:text-(--color-text)"
    }`;

  return (
    <div className="rounded-lg border border-(--color-border) bg-(--color-bg-raised)">
      <div className="flex items-center gap-1 border-b border-(--color-border) px-2 py-1.5" role="tablist">
        <button type="button" role="tab" aria-selected={mode === "write"} className={tabClass(mode === "write")} onClick={() => setMode("write")}>
          Write
        </button>
        <button type="button" role="tab" aria-selected={mode === "preview"} className={tabClass(mode === "preview")} onClick={showPreview}>
          Preview
        </button>
        <span className="ml-auto pr-1 text-xs text-(--color-text-faint)">Markdown</span>
      </div>
      {mode === "write" ? (
        <textarea
          value={value}
          onChange={(event) => onChange(event.target.value)}
          spellCheck
          aria-label="Page text"
          className="block min-h-[26rem] w-full resize-y bg-transparent px-4 py-3 font-mono text-[13.5px] leading-relaxed outline-none"
        />
      ) : (
        <div className="min-h-[26rem] px-5 py-4">
          {preview === null && <p className="text-sm text-(--color-text-faint)">Rendering…</p>}
          {preview !== null && "error" in preview && (
            <p className="text-sm text-(--color-accent-red-text)">Preview failed: {preview.error}</p>
          )}
          {preview !== null && "html" in preview && <Markdown html={preview.html} />}
        </div>
      )}
    </div>
  );
}
