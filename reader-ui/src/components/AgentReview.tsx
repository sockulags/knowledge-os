// Under a review answer in the agent panel (issue #99): each item the agent
// recommended on, with its recommendation and the same one-click actions as
// Decide (DecisionActions, ChangeActions), Undo included. The agent only
// recommends; the person acts here, and the core re-checks every rule.

import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router";
import { api } from "../api/client";
import type { ChangesPayload, DecidePayload } from "../api/types";
import { reviewRecommendations, type Recommendation } from "../lib/agentPrompt";
import { useOnPendingSettled, usePendingEntries, type DecisionEntry } from "../lib/pendingStore";
import { ChangeActions, changeKey } from "./ChangeActions";
import { DecisionActions } from "./DecisionActions";

const RECOMMENDATION_LABELS: Record<Recommendation, string> = {
  accept: "Agent suggests: accept",
  withdraw: "Agent suggests: withdraw",
  discard: "Agent suggests: discard",
  leave: "Agent suggests: leave for now",
};

function current(entries: readonly DecisionEntry[], recordId: string): DecisionEntry | null {
  return (
    entries.find(
      (entry) =>
        entry.meta.recordId === recordId &&
        (entry.state === "waiting" || entry.state === "paused" || entry.state === "saving"),
    ) ?? null
  );
}

export function AgentReview({ text }: { text: string }) {
  const recommendations = reviewRecommendations(text);
  const [decisions, setDecisions] = useState<DecidePayload | null>(null);
  const [changes, setChanges] = useState<ChangesPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const entries = usePendingEntries();

  const load = useCallback(() => {
    Promise.all([api.proposedDecisions(null), api.changes()])
      .then(([decisionPayload, changePayload]) => {
        setDecisions(decisionPayload);
        setChanges(changePayload);
        setError(null);
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Could not load what waits in Decide."));
  }, []);
  useEffect(load, [load]);
  useOnPendingSettled(load);

  if (recommendations.length === 0) return null;
  if (error) return <p className="mt-2 text-xs text-(--color-accent-red-text)">{error}</p>;
  if (decisions === null || changes === null) return null;

  return (
    <div className="mt-3 space-y-2" data-testid="agent-review">
      {recommendations.map((item) => {
        const decision = item.kind === "decision" ? decisions.items.find((row) => row.id === item.id) : undefined;
        const change = item.kind === "change" ? changes.items.find((row) => row.id === item.id) : undefined;
        const title = decision?.title ?? change?.title ?? item.id;
        const href = item.kind === "decision" ? `/r/${item.id}` : `/c/${item.id}`;
        return (
          <div key={`${item.kind}:${item.id}`} className="kos-card px-3 py-2.5 text-sm" data-testid="agent-review-item">
            <Link to={href} className="font-medium text-(--color-text) hover:underline">
              {title}
            </Link>
            <p className="mt-0.5 text-xs text-(--color-text-muted)">
              <span className="font-medium">{RECOMMENDATION_LABELS[item.recommendation]}</span>
              {item.why && ` — ${item.why}`}
            </p>
            <div className="mt-2">
              {decision ? (
                <DecisionActions
                  variant="inline"
                  target={{
                    id: decision.id,
                    title: decision.title,
                    content_sha256: decision.content_sha256,
                    actions: decision.actions,
                    project_id: decision.project.id,
                    folder: "",
                  }}
                  language={decisions.language}
                  pending={current(entries, decision.id)}
                />
              ) : change ? (
                <ChangeActions
                  change={change}
                  labels={changes.labels}
                  noticeLabels={changes.notice_labels}
                  pending={current(entries, changeKey(change.id))}
                />
              ) : (
                <p className="text-xs text-(--color-text-faint)">No longer waits in Decide.</p>
              )}
            </div>
          </div>
        );
      })}
      <Link to="/decide" className="inline-block text-xs text-(--color-accent-text) underline underline-offset-[3px]">
        Open Decide
      </Link>
    </div>
  );
}
