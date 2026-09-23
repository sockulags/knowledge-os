import type { ReactNode } from "react";
import type { WriteFailure } from "../api/types";
import { Callout } from "./Callout";

const HEADLINES: Record<string, string> = {
  validation: "The core did not accept this.",
  duplicate: "Something with this name already exists.",
  not_found: "This page no longer exists.",
  forbidden: "The core refused the request.",
  bad_request: "The request was incomplete.",
  unavailable: "Could not reach the core.",
};

/** A refused write, in place: the core's own message, and any lint issues
 * it found in the result, one per line. Conflicts have their own callout
 * (see ConflictCallout) because they offer a reload. */
export function WriteFailureCallout({ failure, children }: { failure: WriteFailure; children?: ReactNode }) {
  return (
    <Callout tone="danger">
      <p className="font-medium">{HEADLINES[failure.error] ?? "Nothing was saved."}</p>
      {/* With lint issues, the detail only repeats them (with the core's
          temporary staging path), so show the issues alone. */}
      {!(failure.issues && failure.issues.length > 0) && (
        <p className="mt-1 whitespace-pre-wrap break-words">{failure.detail}</p>
      )}
      {failure.issues && failure.issues.length > 0 && (
        <ul className="mt-2 space-y-1">
          {failure.issues.map((issue, index) => (
            <li key={index}>
              <span className="break-all font-mono text-xs opacity-90">{issue.path}</span>
              <span className="block">{issue.message}</span>
            </li>
          ))}
        </ul>
      )}
      {children}
    </Callout>
  );
}

export function ConflictCallout({ onReload, onKeepEditing }: { onReload: () => void; onKeepEditing?: () => void }) {
  return (
    <Callout tone="danger">
      <p className="font-medium">This file changed on disk after you opened it.</p>
      <p className="mt-1">
        Nothing was saved. Reload to see the current version; your edits here are discarded when you do, so copy
        anything you want to keep first.
      </p>
      <div className="mt-3 flex gap-2">
        <button
          type="button"
          onClick={onReload}
          className="rounded-md bg-(--color-accent-red-text) px-3 py-1.5 text-sm font-medium text-white hover:opacity-90"
        >
          Reload current version
        </button>
        {onKeepEditing && (
          <button
            type="button"
            onClick={onKeepEditing}
            className="rounded-md px-3 py-1.5 text-sm hover:bg-(--color-bg-hover)"
          >
            Keep my text for now
          </button>
        )}
      </div>
    </Callout>
  );
}
