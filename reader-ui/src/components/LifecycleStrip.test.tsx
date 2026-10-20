import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import type { DecisionLanguage } from "../api/types";
import { changeLifecycle, decisionLifecycle, LifecycleStrip, recordLifecycle } from "./LifecycleStrip";

const language = {
  guide: {
    states: [
      { key: "proposed", label: "Proposed", text: "" },
      { key: "in_force", label: "In force", text: "" },
      { key: "replaced", label: "Replaced", text: "" },
      { key: "withdrawn", label: "Withdrawn", text: "" },
    ],
  },
} as unknown as DecisionLanguage;

afterEach(cleanup);

function currentLabel(): string | null {
  return screen.getByRole("img").querySelector("[data-current]")?.textContent ?? null;
}

describe("LifecycleStrip", () => {
  it.each([
    ["draft", "Proposed", "Lifecycle: Proposed (now), then In force, then Replaced or Withdrawn"],
    ["active", "In force", "Lifecycle: Proposed, then In force (now), then Replaced or Withdrawn"],
    ["superseded", "Replaced", "Lifecycle: Proposed, then In force, then Replaced (now) or Withdrawn"],
    ["archived", "Withdrawn", "Lifecycle: Proposed, then In force, then Replaced or Withdrawn (now)"],
  ])("highlights a %s decision as %s", (status, label, sentence) => {
    render(<LifecycleStrip lifecycle={decisionLifecycle(language, status)!} />);
    const strip = screen.getByRole("img", { name: sentence });
    expect(currentLabel()).toBe(label);
    // Every stage keeps a visible label, not only the current one.
    for (const word of ["Proposed", "In force", "Replaced", "Withdrawn"]) expect(strip.textContent).toContain(word);
  });

  it.each([
    ["draft", "Draft"],
    ["active", "Current"],
    ["superseded", "Replaced"],
    ["archived", "Archived"],
    ["deprecated", "Discouraged"],
  ])("highlights a %s page that is not a decision as %s", (status, label) => {
    render(<LifecycleStrip lifecycle={recordLifecycle(status)!} />);
    expect(screen.getByRole("img").getAttribute("data-stage")).toBe(status);
    expect(currentLabel()).toBe(label);
    expect(screen.getByRole("img").getAttribute("aria-label")).toContain(`${label} (now)`);
  });

  it("draws nothing for a status outside the lifecycle", () => {
    expect(decisionLifecycle(language, "deprecated")).toBeNull();
    expect(recordLifecycle("proposed")).toBeNull();
  });

  it("falls back to its own words when the guide is missing", () => {
    render(<LifecycleStrip lifecycle={decisionLifecycle(null, "active")!} />);
    expect(currentLabel()).toBe("In force");
  });

  it("shows a proposed change with the review rule beside it", () => {
    render(<LifecycleStrip lifecycle={changeLifecycle()} note="Rule: decisions need review" />);
    expect(screen.getByRole("img", { name: "Lifecycle: Proposed (now), then Accepted or Discarded" })).toBeTruthy();
    expect(screen.getByText("Rule: decisions need review")).toBeTruthy();
  });
});
