import { useState } from "react";
import { ShieldAlert } from "lucide-react";
import { codexTurnedOn, turnOnCodex } from "../lib/codexAccess";

const WHAT_IT_CAN_DO =
  "Codex's own tools cannot be turned off: it can read any file your account can on this computer, not only this knowledge base, without asking, and the MCP servers in your own ~/.codex/config.toml load too. Writing files and network access still ask you.";

/**
 * Shown in the agent panel while Codex is the agent (decision
 * `in-app-agent-provider-isolation`): first a card the person must confirm
 * before Codex starts, then a one-line notice for as long as Codex is used.
 */
export function CodexNotice({ onTurnedOn }: { onTurnedOn: () => void }) {
  const [on, setOn] = useState(codexTurnedOn);
  if (on) {
    return (
      <p
        className="flex items-start gap-1.5 border-b border-(--color-border) bg-(--color-accent-amber-bg) px-3 py-1.5 text-xs text-(--color-accent-amber-text)"
        role="note"
        data-testid="agent-codex-notice"
        title={WHAT_IT_CAN_DO}
      >
        <ShieldAlert size={13} className="mt-px shrink-0" />
        Codex is less isolated than Claude Code: it can read files outside this knowledge base.
      </p>
    );
  }
  return (
    <div
      className="border-b border-(--color-border) bg-(--color-accent-amber-bg) px-3 py-2.5 text-sm text-(--color-accent-amber-text)"
      role="note"
      data-testid="agent-codex-opt-in"
    >
      <p className="flex items-center gap-1.5 font-medium">
        <ShieldAlert size={14} className="shrink-0" />
        Codex is less isolated than Claude Code
      </p>
      <p className="mt-1 text-xs">{WHAT_IT_CAN_DO}</p>
      <label className="mt-2 flex cursor-pointer items-center gap-2 text-xs font-medium">
        <input
          type="checkbox"
          className="accent-(--color-accent)"
          checked={false}
          onChange={() => {
            turnOnCodex();
            setOn(true);
            onTurnedOn();
          }}
        />
        Use Codex with this access
      </label>
    </div>
  );
}
