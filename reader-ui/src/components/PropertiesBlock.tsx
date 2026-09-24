import { useState, type ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import type { PropertiesBlock as PropertiesBlockData } from "../api/types";
import { Pill } from "./Pill";

const SOURCE_VISIBLE = 3;

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[100px_1fr] gap-3 py-2 text-sm sm:grid-cols-[124px_1fr]">
      <dt className="text-(--color-text-faint)">{label}</dt>
      <dd className="min-w-0">{children}</dd>
    </div>
  );
}

/** The two-column properties block under a document's title:
 * Status, Trust, Applies to, Updated, Source. A long provenance list
 * collapses to "N sources" with an expander (design brief). */
export function PropertiesBlock({ properties }: { properties: PropertiesBlockData }) {
  const [sourceOpen, setSourceOpen] = useState(false);
  const sources = Array.isArray(properties.source.value) ? properties.source.value : [];
  const showToggle = sources.length > SOURCE_VISIBLE;
  const visibleSources = sourceOpen ? sources : sources.slice(0, SOURCE_VISIBLE);

  return (
    <dl className="kos-card mb-8 divide-y divide-(--color-border) px-4 py-0.5">
      <Row label={properties.status.label}>
        <div className="flex flex-wrap items-center gap-2">
          {properties.status.pill && <Pill pill={properties.status.pill} />}
          <span>{properties.status.value}</span>
        </div>
      </Row>
      {properties.trust && (
        <Row label={properties.trust.label}>
          <div className="flex flex-wrap items-center gap-2">
            {properties.trust.pill && <Pill pill={properties.trust.pill} />}
            <span>{properties.trust.value}</span>
          </div>
        </Row>
      )}
      <Row label={properties.applies_to.label}>{properties.applies_to.value}</Row>
      <Row label={properties.updated.label}>
        <span title={properties.updated.raw}>{properties.updated.value}</span>
      </Row>
      <Row label={properties.source.label}>
        {sources.length === 0 ? (
          <span className="text-(--color-text-faint)">—</span>
        ) : (
          <div className="space-y-1">
            {visibleSources.map((sentence, index) => (
              <p key={index}>{sentence}</p>
            ))}
            {showToggle && (
              <button
                type="button"
                onClick={() => setSourceOpen((open) => !open)}
                className="-mx-1 inline-flex items-center gap-1 rounded-(--radius-control) px-1 text-(--color-text-muted) hover:text-(--color-accent-text)"
              >
                <ChevronDown size={14} className={sourceOpen ? "rotate-180 transition-transform" : "transition-transform"} />
                {sourceOpen ? "Show fewer" : `${sources.length} sources`}
              </button>
            )}
          </div>
        )}
      </Row>
    </dl>
  );
}
