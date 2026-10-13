import { useRef, useState, type ClipboardEvent, type DragEvent } from "react";
import { Paperclip } from "lucide-react";
import { write, type AttachTarget } from "../api/write";
import { Markdown } from "./Markdown";

/** Largest file the core attaches (`attachments.MAX_ATTACHMENT_BYTES`). */
const MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024;

/** The file's bytes as base64, without the `data:...;base64,` prefix. */
function readBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const url = String(reader.result);
      resolve(url.slice(url.indexOf(",") + 1));
    };
    reader.onerror = () => reject(reader.error ?? new Error("The file could not be read."));
    reader.readAsDataURL(file);
  });
}

/** A pasted screenshot arrives as "image.png"; name it after the moment
 * instead, so several pastes read apart in the assets folder. */
function uploadName(file: File, pasted: boolean): string {
  if (!pasted || !/^image\.\w+$/i.test(file.name)) return file.name || "file";
  const stamp = new Date().toISOString().slice(0, 19).replace(/[-:]/g, "").replace("T", "-");
  return `pasted-${stamp}${file.name.slice(file.name.lastIndexOf("."))}`;
}

/** A plain Markdown textarea with a Write / Preview toggle. The preview is
 * rendered by the core (POST /api/preview), so it matches the record page.
 * With `attachTo`, images and files can be pasted, dropped, or chosen: each
 * is stored in the `assets/` folder next to the page and linked where the
 * cursor was. */
export function MarkdownEditor({
  value,
  onChange,
  path,
  attachTo,
}: {
  value: string;
  onChange: (value: string) => void;
  /** The record's path, so relative links in the preview resolve like on the page. */
  path?: string;
  /** Where attached files go; without it the editor attaches nothing. */
  attachTo?: AttachTarget;
}) {
  const [mode, setMode] = useState<"write" | "preview">("write");
  const [preview, setPreview] = useState<{ html: string } | { error: string } | null>(null);
  const [uploading, setUploading] = useState(0);
  const [attachError, setAttachError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  // The latest text, for uploads that finish after more typing.
  const valueRef = useRef(value);
  valueRef.current = value;

  async function showPreview() {
    setMode("preview");
    setPreview(null);
    const outcome = await write.preview(value, path);
    setPreview(outcome.ok ? { html: outcome.data.html } : { error: outcome.failure.detail });
  }

  function insertAtCursor(text: string): void {
    const current = valueRef.current;
    const area = textareaRef.current;
    const start = area ? area.selectionStart : current.length;
    const end = area ? area.selectionEnd : current.length;
    const next = current.slice(0, start) + text + current.slice(end);
    valueRef.current = next;
    onChange(next);
    requestAnimationFrame(() => {
      if (!textareaRef.current) return;
      textareaRef.current.selectionStart = textareaRef.current.selectionEnd = start + text.length;
    });
  }

  function replaceOnce(placeholder: string, text: string): void {
    const current = valueRef.current;
    const at = current.indexOf(placeholder);
    const next = at === -1 ? current + text : current.slice(0, at) + text + current.slice(at + placeholder.length);
    valueRef.current = next;
    onChange(next);
  }

  async function attach(files: File[], pasted: boolean): Promise<void> {
    if (!attachTo || files.length === 0) return;
    setAttachError(null);
    for (const file of files) {
      const name = uploadName(file, pasted);
      if (file.size > MAX_ATTACHMENT_BYTES) {
        setAttachError(`“${name}” is larger than 25 MB. Keep large media outside the knowledge base and link to it.`);
        continue;
      }
      // Marks where the link goes while the file is stored.
      const placeholder = `[Attaching ${name}…]()`;
      insertAtCursor(placeholder);
      setUploading((count) => count + 1);
      try {
        const outcome = await write.attach(attachTo, name, await readBase64(file));
        if (outcome.ok) {
          replaceOnce(placeholder, outcome.data.markdown);
        } else {
          replaceOnce(placeholder, "");
          setAttachError(`“${name}” was not attached: ${outcome.failure.detail}`);
        }
      } catch (error) {
        replaceOnce(placeholder, "");
        setAttachError(`“${name}” could not be read: ${error instanceof Error ? error.message : String(error)}`);
      } finally {
        setUploading((count) => count - 1);
      }
    }
  }

  function handlePaste(event: ClipboardEvent<HTMLTextAreaElement>) {
    if (!attachTo) return;
    const files = Array.from(event.clipboardData.files);
    if (files.length === 0) return;
    event.preventDefault();
    void attach(files, true);
  }

  function handleDrop(event: DragEvent<HTMLTextAreaElement>) {
    setDragging(false);
    if (!attachTo) return;
    const files = Array.from(event.dataTransfer.files);
    if (files.length === 0) return;
    event.preventDefault();
    // Put the cursor where the file was dropped when the browser can say.
    textareaRef.current?.focus();
    void attach(files, false);
  }

  const tabClass = (active: boolean) =>
    `rounded-[5px] px-3 py-1 text-[13px] transition-colors ${
      active
        ? "bg-(--color-bg-raised) font-medium text-(--color-text) shadow-[0_1px_2px_rgb(0_0_0/0.08)] ring-1 ring-(--color-border)"
        : "text-(--color-text-muted) hover:text-(--color-text)"
    }`;

  return (
    <div className="overflow-hidden rounded-(--radius-card) border border-(--color-border-strong) bg-(--color-bg-raised) transition-[border-color,box-shadow] duration-100 focus-within:border-(--color-focus) focus-within:shadow-[0_0_0_3px_color-mix(in_srgb,var(--color-focus)_22%,transparent)]">
      <div className="flex items-center gap-1 border-b border-(--color-border) bg-(--color-bg-sidebar) px-2 py-1.5" role="tablist">
        <button type="button" role="tab" aria-selected={mode === "write"} className={tabClass(mode === "write")} onClick={() => setMode("write")}>
          Write
        </button>
        <button type="button" role="tab" aria-selected={mode === "preview"} className={tabClass(mode === "preview")} onClick={showPreview}>
          Preview
        </button>
        {attachTo && mode === "write" && (
          <>
            <button
              type="button"
              className="ml-2 inline-flex items-center gap-1.5 rounded-[5px] px-2.5 py-1 text-[13px] text-(--color-text-muted) transition-colors hover:text-(--color-text)"
              onClick={() => fileInputRef.current?.click()}
              title="Attach an image or a file. You can also paste or drop one into the text."
            >
              <Paperclip className="size-3.5" aria-hidden />
              {uploading > 0 ? "Attaching…" : "Attach file"}
            </button>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              hidden
              onChange={(event) => {
                const files = Array.from(event.target.files ?? []);
                event.target.value = "";
                void attach(files, false);
              }}
            />
          </>
        )}
        <span className="ml-auto pr-1.5 text-xs text-(--color-text-faint)">Markdown</span>
      </div>
      {attachError && (
        <p role="alert" className="border-b border-(--color-border) px-5 py-2 text-[13px] text-(--color-accent-red-text)">
          {attachError}
        </p>
      )}
      {mode === "write" ? (
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onPaste={handlePaste}
          onDrop={handleDrop}
          onDragOver={(event) => {
            if (attachTo && event.dataTransfer.types.includes("Files")) {
              event.preventDefault();
              setDragging(true);
            }
          }}
          onDragLeave={() => setDragging(false)}
          spellCheck
          aria-label="Page text"
          className={`block min-h-[26rem] w-full resize-y bg-transparent px-5 py-4 font-mono text-[13.5px] leading-[1.7] text-(--color-text) outline-none focus-visible:outline-none ${
            dragging ? "bg-(--color-accent-ink-bg)" : ""
          }`}
        />
      ) : (
        <div className="min-h-[26rem] px-6 py-5">
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
