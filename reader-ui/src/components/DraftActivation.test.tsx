import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { DraftActivation as DraftActivationData } from "../api/types";
import { write } from "../api/write";
import { decisionKey, pendingActions } from "../lib/pendingStore";
import { DraftActivation } from "./DraftActivation";

vi.mock("../api/write", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/write")>()),
  write: { activate: vi.fn(async () => ({ ok: true, data: {} })) },
}));

const SHA = "a".repeat(64);

const activation = {
  summary: "Work in progress. It does not count as current knowledge until you make it active.",
  label: "Make active",
  labels: { undo: "Undo", saving: "Saving…", conflict: "Changed on disk." },
  outcome: {
    notice: "Made “Retry policy” active.",
    summary: "Made active. It is current from today.",
    status: { label: "Status", value: "Current", pill: null },
  },
} as unknown as DraftActivationData;

afterEach(async () => {
  cleanup();
  await pendingActions.flushAll();
});

describe("DraftActivation", () => {
  it("makes the draft active after the undo window, with the hash the page was read at", async () => {
    render(<DraftActivation id="retry-policy" sha={SHA} activation={activation} />);
    expect(screen.getByText(activation.summary)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Make active" }));

    const entry = pendingActions.entry(decisionKey("retry-policy"));
    expect(entry?.kind).toBe("activate");
    expect(entry?.meta.outcome.summary).toBe("Made active. It is current from today.");
    expect(write.activate).not.toHaveBeenCalled();

    await pendingActions.flushAll();
    expect(write.activate).toHaveBeenCalledWith("retry-policy", SHA, expect.anything());
  });

  it("shows the outcome with Undo while the write waits", () => {
    render(<DraftActivation id="undo-policy" sha={SHA} activation={activation} />);
    fireEvent.click(screen.getByRole("button", { name: "Make active" }));
    const entry = pendingActions.entry(decisionKey("undo-policy"))!;
    cleanup();

    render(<DraftActivation id="undo-policy" sha={SHA} activation={activation} pending={entry} />);
    expect(screen.getByRole("status").textContent).toContain("Made active. It is current from today.");
    fireEvent.click(screen.getByRole("button", { name: "Undo" }));

    expect(pendingActions.entry(decisionKey("undo-policy"))?.state).toBe("undone");
  });
});
