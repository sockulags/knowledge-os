import { useState } from "react";
import { ChevronRight } from "lucide-react";
import type { TechnicalDetails as TechnicalDetailsData } from "../api/types";

/** The collapsed "Technical details" toggle: the exact contract values
 * (status, trust label, scope, record_kind, path, content_sha256, raw
 * provenance), never shown outside this one block. */
export function TechnicalDetails({ details }: { details: TechnicalDetailsData }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mb-8 rounded-lg border border-(--color-border)">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center gap-1.5 px-4 py-2.5 text-sm text-(--color-text-muted) hover:text-(--color-text)"
      >
        <ChevronRight size={14} className={open ? "rotate-90 transition-transform" : "transition-transform"} />
        Technical details
      </button>
      {open && (
        <div className="border-t border-(--color-border) px-4 py-3">
          <dl className="grid grid-cols-[140px_1fr] gap-x-3 gap-y-1.5 font-mono text-xs">
            <dt className="text-(--color-text-faint)">status</dt>
            <dd className="break-all">{details.status}</dd>
            <dt className="text-(--color-text-faint)">trust_label</dt>
            <dd className="break-all">{details.trust_label}</dd>
            <dt className="text-(--color-text-faint)">scope</dt>
            <dd className="break-all">{details.scope}</dd>
            <dt className="text-(--color-text-faint)">record_kind</dt>
            <dd className="break-all">{details.record_kind ?? "—"}</dd>
            <dt className="text-(--color-text-faint)">path</dt>
            <dd className="break-all">{details.path}</dd>
            <dt className="text-(--color-text-faint)">content_sha256</dt>
            <dd className="break-all">{details.content_sha256}</dd>
          </dl>
          {details.provenance.length > 0 && (
            <div className="mt-4 overflow-x-auto">
              <table className="w-full min-w-[420px] border-collapse font-mono text-xs">
                <thead>
                  <tr className="text-left text-(--color-text-faint)">
                    <th className="pb-1 pr-3 font-normal">kind</th>
                    <th className="pb-1 pr-3 font-normal">reference</th>
                    <th className="pb-1 pr-3 font-normal">captured</th>
                    <th className="pb-1 font-normal">sha256</th>
                  </tr>
                </thead>
                <tbody>
                  {details.provenance.map((entry, index) => (
                    <tr key={index} className="border-t border-(--color-border)">
                      <td className="py-1 pr-3 align-top">{entry.kind}</td>
                      <td className="py-1 pr-3 align-top break-all">{entry.reference}</td>
                      <td className="py-1 pr-3 align-top">{entry.captured ?? "—"}</td>
                      <td className="py-1 align-top break-all">{entry.sha256 ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
