import { useRef, type MouseEvent } from "react";
import { useNavigate } from "react-router";

/** Renders `body_html` (already-sanitized HTML from knowledge_os/reader's
 * markdown.py: it parses with `html=False`, so raw HTML from source
 * content is always escaped, never executed). The one piece of behaviour
 * this adds client-side is link interception: an internal link
 * (`href` starting with "/", e.g. "/r/some-id") navigates through the
 * router instead of a full page reload, per the design brief. */
export function Markdown({ html, className }: { html: string; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  function handleClick(event: MouseEvent<HTMLDivElement>) {
    const target = (event.target as HTMLElement).closest("a");
    if (!target) return;
    const href = target.getAttribute("href");
    if (!href || !href.startsWith("/")) return;
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    navigate(href);
  }

  return (
    <div
      ref={ref}
      className={`prose-kos ${className ?? ""}`}
      onClick={handleClick}
      // eslint-disable-next-line react/no-danger
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
