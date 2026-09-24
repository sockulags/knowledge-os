import { useEffect, useState } from "react";
import type { Heading } from "../api/types";

/** Sticky right-side "On this page" table of contents, shown on screens
 * 1280px and wider for documents with three or more headings (design
 * brief); hidden below that width rather than squeezing the reading
 * column. Highlights the section currently in view. */
export function TableOfContents({ headings }: { headings: Heading[] }) {
  const [activeAnchor, setActiveAnchor] = useState<string | null>(null);

  useEffect(() => {
    if (headings.length === 0) return;
    const elements = headings
      .map(([, , anchor]) => document.getElementById(anchor))
      .filter((el): el is HTMLElement => el !== null);
    if (elements.length === 0) return;

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setActiveAnchor(entry.target.id);
            break;
          }
        }
      },
      { rootMargin: "-88px 0px -70% 0px", threshold: 0 },
    );
    elements.forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, [headings]);

  if (headings.length < 3) return null;

  return (
    <nav
      aria-label="On this page"
      className="hidden xl:block sticky top-20 max-h-[calc(100vh-6rem)] w-56 shrink-0 overflow-y-auto self-start pl-2 text-sm"
    >
      <p className="kos-eyebrow mb-2.5">On this page</p>
      <ul className="space-y-1 border-l border-(--color-border)">
        {headings.map(([level, text, anchor]) => (
          <li key={anchor} style={{ paddingLeft: `${(level - 1) * 0.65 + 0.65}rem` }}>
            <a
              href={`#${anchor}`}
              className={`-ml-px block border-l-2 py-0.5 pl-2 text-[13px] leading-snug transition-colors ${
                activeAnchor === anchor
                  ? "border-(--color-accent) font-medium text-(--color-text)"
                  : "border-transparent text-(--color-text-muted) hover:text-(--color-text)"
              }`}
            >
              {text}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}
