import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import type { DecisionLanguage, PendingObservation, PendingObservationsPayload } from "../api/types";
import { api } from "../api/client";
import { observations } from "../api/write";
import { pendingActions } from "../lib/pendingStore";
import { PendingObservations } from "./PendingObservations";
import { UndoNotices } from "./UndoNotices";

vi.mock("../api/client", () => ({ api: { pendingObservations: vi.fn() } }));
vi.mock("../api/write", () => ({ observations: { review: vi.fn() } }));

const labels = {
  related: "Pages it may overlap with",
  no_related: "No page it may overlap with was found.",
  packet: "Review packet",
  agent: "Ask your agent",
  commands: "Or run one of these",
  copy: "Copy",
  copied: "Copied",
  act_retain: "Keep",
  act_reject: "Dismiss…",
  act_promote: "Turn into a page…",
  reason_label: "Why dismiss it?",
  reason_placeholder: "Required",
  confirm_reject: "Dismiss",
  promote_title: "Title of the new page",
  promote_id: "Page ID",
  promote_general: "Make it general knowledge instead of a page in {project}",
  acknowledge_related: "I have checked the pages it may overlap with",
  confirm_promote: "Create draft page",
  cancel: "Cancel",
  notice_retain: "Kept “{title}” as a reviewed observation.",
  notice_reject: "Dismissed “{title}”.",
  notice_promote: "Turning “{title}” into a new draft page.",
  failed: "Could not review “{title}”:",
};

const noticeLabels = {
  undo: "Undo",
  dismiss: "Dismiss notice",
  undone: "Undone. Nothing was changed.",
  saving: "Saving…",
  failed: "Could not save.",
} as unknown as DecisionLanguage["labels"];

const SHA = "a".repeat(64);

function observation(id: string, title: string, overrides: Partial<PendingObservation> = {}): PendingObservation {
  return {
    id,
    title,
    excerpt: "",
    project: { id: "demo", title: "Demo" },
    proposed_by: { source: "other", label: "An agent run" },
    proposed_display: null,
    proposed_exact: null,
    trust: "Observation — not knowledge",
    status_pill: null,
    related: [],
    packet_html: null,
    agent_phrase: `Review the discovery ${id} in Knowledge OS.`,
    commands: [],
    content_sha256: SHA,
    scope: "project:demo",
    actions: {
      retain: true,
      promote: { target_id: id, title, acknowledge_related: false, allow_scope_broadening: true },
    },
    ...overrides,
  };
}

function payload(items: PendingObservation[]): PendingObservationsPayload {
  return {
    heading: "Observations waiting",
    intro: "Not knowledge until reviewed.",
    count: items.length,
    count_label: null,
    error: null,
    items,
    labels,
    notice_labels: noticeLabels,
  };
}

const friday = observation("friday-deploys", "Deploys fail on Fridays", {
  related: [{ id: "deploy-freeze", title: "Deploy freeze on Fridays", reasons: ["FTS"], exists: true }],
  actions: {
    retain: true,
    promote: {
      target_id: "deploys-fail-on-fridays",
      title: "Deploys fail on Fridays",
      acknowledge_related: true,
      allow_scope_broadening: true,
    },
  },
});
const slow = observation("slow-tests", "Tests are slow");

async function show(items: PendingObservation[]) {
  vi.mocked(api.pendingObservations).mockResolvedValue(payload(items));
  const onCount = vi.fn();
  render(
    <MemoryRouter>
      <PendingObservations onCount={onCount} />
      <UndoNotices />
    </MemoryRouter>,
  );
  await screen.findByTestId("pending-observations");
  return onCount;
}

function row(title: string) {
  const rows = screen.getAllByTestId("observation-row");
  const found = rows.find((item) => item.textContent?.includes(title));
  if (!found) throw new Error(`no row ${title}`);
  return found;
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(observations.review).mockResolvedValue({ ok: true, data: {} as never });
});

afterEach(async () => {
  for (const entry of pendingActions.snapshot()) pendingActions.undo(entry.id);
  for (const entry of pendingActions.snapshot()) pendingActions.dismiss(entry.id);
  cleanup();
});

describe("Reviewing observations in Decide", () => {
  it("keeps one: the row goes at once and the request waits for the undo window", async () => {
    const onCount = await show([friday, slow]);
    expect(onCount).toHaveBeenLastCalledWith(2);
    fireEvent.click(within(row("Tests are slow")).getByRole("button", { name: "Keep" }));

    expect(screen.getAllByTestId("observation-row")).toHaveLength(1);
    expect(onCount).toHaveBeenLastCalledWith(1);
    expect(screen.getByText("Kept “Tests are slow” as a reviewed observation.")).toBeTruthy();
    expect(observations.review).not.toHaveBeenCalled();

    await act(() => pendingActions.flushAll());
    expect(observations.review).toHaveBeenCalledTimes(1);
    expect(vi.mocked(observations.review).mock.calls[0].slice(0, 3)).toEqual([
      "slow-tests",
      "retain",
      { expected_sha256: SHA },
    ]);
  });

  it("dismisses one only with a reason", async () => {
    await show([slow]);
    fireEvent.click(within(row("Tests are slow")).getByRole("button", { name: "Dismiss…" }));
    const confirm = within(row("Tests are slow")).getByRole("button", { name: "Dismiss" }) as HTMLButtonElement;
    expect(confirm.disabled).toBe(true);
    fireEvent.change(within(row("Tests are slow")).getByLabelText("Why dismiss it?"), { target: { value: " not true " } });
    expect(confirm.disabled).toBe(false);
    fireEvent.click(confirm);

    expect(screen.queryByTestId("pending-observations")).toBeNull();
    await act(() => pendingActions.flushAll());
    expect(vi.mocked(observations.review).mock.calls[0].slice(0, 3)).toEqual([
      "slow-tests",
      "reject",
      { expected_sha256: SHA, reason: "not true" },
    ]);
  });

  it("promotes one with the flags its packet needs", async () => {
    await show([friday]);
    fireEvent.click(within(row("Deploys fail on Fridays")).getByRole("button", { name: "Turn into a page…" }));
    const form = row("Deploys fail on Fridays");
    const create = within(form).getByRole("button", { name: "Create draft page" }) as HTMLButtonElement;
    // Related pages were found: promoting waits until they are acknowledged.
    expect(create.disabled).toBe(true);
    fireEvent.click(within(form).getByLabelText("I have checked the pages it may overlap with"));
    fireEvent.click(within(form).getByLabelText("Make it general knowledge instead of a page in Demo"));
    fireEvent.change(within(form).getByLabelText("Title of the new page"), { target: { value: "Friday rule" } });
    fireEvent.change(within(form).getByLabelText("Page ID"), { target: { value: "friday-rule" } });
    fireEvent.click(create);

    await act(() => pendingActions.flushAll());
    expect(vi.mocked(observations.review).mock.calls[0].slice(0, 3)).toEqual([
      "friday-deploys",
      "promote",
      {
        expected_sha256: SHA,
        target_id: "friday-rule",
        title: "Friday rule",
        scope: "general",
        acknowledge_related: true,
        allow_scope_broadening: true,
      },
    ]);
  });

  it("offers no checkboxes when the packet's flags do not apply", async () => {
    await show([
      observation("general-note", "General note", {
        scope: "general",
        actions: {
          retain: false,
          promote: { target_id: "general-note", title: "General note", acknowledge_related: false, allow_scope_broadening: false },
        },
      }),
    ]);
    const item = row("General note");
    expect(within(item).queryByRole("button", { name: "Keep" })).toBeNull();
    fireEvent.click(within(item).getByRole("button", { name: "Turn into a page…" }));
    expect(within(item).queryByRole("checkbox")).toBeNull();
    fireEvent.click(within(item).getByRole("button", { name: "Create draft page" }));
    await act(() => pendingActions.flushAll());
    expect(vi.mocked(observations.review).mock.calls[0][2]).toEqual({
      expected_sha256: SHA,
      target_id: "general-note",
      title: "General note",
      scope: "general",
      acknowledge_related: false,
      allow_scope_broadening: false,
    });
  });

  it("undo brings the row back and sends nothing", async () => {
    await show([slow]);
    fireEvent.click(within(row("Tests are slow")).getByRole("button", { name: "Keep" }));
    expect(screen.queryByTestId("pending-observations")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Undo" }));
    expect(screen.getAllByTestId("observation-row")).toHaveLength(1);
    await act(() => pendingActions.flushAll());
    expect(observations.review).not.toHaveBeenCalled();
  });

  it("shows a refusal inline on the row it brings back", async () => {
    vi.mocked(observations.review).mockResolvedValue({
      ok: false,
      status: 409,
      failure: { error: "conflict", detail: "This observation changed after it was shown." },
    });
    await show([slow]);
    fireEvent.click(within(row("Tests are slow")).getByRole("button", { name: "Keep" }));
    await act(() => pendingActions.flushAll());
    const item = await screen.findByTestId("observation-row");
    expect(within(item).getByText("Could not review “Tests are slow”:")).toBeTruthy();
    expect(within(item).getByText("This observation changed after it was shown.")).toBeTruthy();
  });
});
