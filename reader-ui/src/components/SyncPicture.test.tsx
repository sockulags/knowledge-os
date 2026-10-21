import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import type { SyncStatus } from "../api/types";
import { SyncPicture } from "./SyncPicture";

const base: SyncStatus = {
  setup: { state: "ready", sentence: null, label: null },
  available: true,
  reason: null,
  detail: null,
  branch: "main",
  upstream: "origin/main",
  remotes: ["origin"],
  ahead: 0,
  behind: 0,
  uncommitted: 0,
  merging: false,
  conflicts: 0,
  last_sync: null,
  identity: { name: "Ada", email: "ada@example.com" },
  warnings: [],
};

afterEach(cleanup);

function picture(overrides: Partial<SyncStatus>) {
  render(<SyncPicture status={{ ...base, ...overrides }} />);
  return screen.getByRole("img");
}

describe("SyncPicture", () => {
  it("shows commits to push and to pull on their own arrows", () => {
    const img = picture({ ahead: 2, behind: 1 });
    expect(img.getAttribute("data-state")).toBe("waiting");
    expect(img.getAttribute("aria-label")).toBe("This computer (main) and origin/main: 2 commits to push, 1 commit to pull.");
    expect(img.querySelector('[data-lane="push"]')?.getAttribute("data-count")).toBe("2");
    expect(img.querySelector('[data-lane="pull"]')?.getAttribute("data-count")).toBe("1");
    expect(screen.getByText("2 commits to push")).toBeTruthy();
    expect(screen.getByText("1 commit to pull")).toBeTruthy();
  });

  it("says both sides match when nothing waits", () => {
    const img = picture({});
    expect(img.getAttribute("data-state")).toBe("in-step");
    expect(img.getAttribute("aria-label")).toContain("Both sides match");
    expect(screen.getByText("Nothing to push")).toBeTruthy();
    expect(screen.getByText("Nothing to pull")).toBeTruthy();
  });

  it("marks a sync stopped on conflicts", () => {
    const img = picture({ merging: true, conflicts: 3, behind: 4 });
    expect(img.getAttribute("data-state")).toBe("conflict");
    expect(img.getAttribute("aria-label")).toContain("3 files have changed on both sides and need a version.");
    expect(screen.getByText("3 conflicts")).toBeTruthy();
  });

  it("shows the remote as missing when there is no upstream", () => {
    const img = picture({ upstream: null, remotes: [], ahead: 5 });
    expect(img.getAttribute("data-state")).toBe("no-remote");
    expect(img.getAttribute("aria-label")).toBe("This computer (main) has nowhere to sync to yet.");
    expect(screen.getByText("No remote")).toBeTruthy();
    expect(img.querySelector("[data-lane]")).toBeNull();
  });

  it("notes uncommitted files on this computer", () => {
    picture({ uncommitted: 2 });
    expect(screen.getByText("main · 2 not committed")).toBeTruthy();
  });

  it("draws nothing when the knowledge base is not in Git", () => {
    const { container } = render(<SyncPicture status={{ ...base, available: false }} />);
    expect(container.innerHTML).toBe("");
  });
});
