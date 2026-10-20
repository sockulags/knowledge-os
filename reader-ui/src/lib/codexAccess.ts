// Codex is less isolated than Claude Code in the app (decision
// `in-app-agent-provider-isolation`): its built-in tools cannot be turned off,
// its read-only sandbox does not limit which files it reads, and the MCP
// servers in the person's own ~/.codex/config.toml load too. So it is not
// started until the person turns it on in the agent panel. The choice is
// remembered like the chosen agent; without storage it lasts until reload.

const CODEX = "codex";
const KEY = "kos.agent.codexTurnedOn";

let fallback = false;

/** Whether this provider waits for the person to turn it on. */
export function needsTurningOn(providerId: string | null): boolean {
  return providerId === CODEX && !codexTurnedOn();
}

export function isCodex(providerId: string | null | undefined): boolean {
  return providerId === CODEX;
}

export function codexTurnedOn(): boolean {
  try {
    return window.localStorage.getItem(KEY) === "yes" || fallback;
  } catch {
    return fallback;
  }
}

export function turnOnCodex(): void {
  fallback = true;
  try {
    window.localStorage.setItem(KEY, "yes");
  } catch {
    // Remembering the choice is a convenience only.
  }
}
