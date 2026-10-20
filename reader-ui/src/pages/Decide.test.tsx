import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { createMemoryRouter, Outlet, RouterProvider } from "react-router";
import type { ChangesPayload, DecidePayload, ReviewRulesPayload } from "../api/types";
import { api } from "../api/client";
import { forgetReviewRules } from "../components/ReviewRules";
import { Decide } from "./Decide";

vi.mock("../api/client", () => ({
  api: { proposedDecisions: vi.fn(), changes: vi.fn(), reviewRules: vi.fn() },
}));
vi.mock("../components/DecisionGuide", () => ({ DecisionGuideToggle: () => null }));

const decide = {
  title: "Decide",
  intro: "What waits for you.",
  count: 0,
  count_label: null,
  count_templates: { one: "1 decision", other: "{count} decisions" },
  project: null,
  filter_label: "Projects",
  all_projects_label: "All",
  projects: [],
  items: [],
  empty: { title: "Nothing to decide", body: "All clear." },
  open_label: "Open",
  language: {},
} as unknown as DecidePayload;

const changes = {
  heading: "Proposed changes",
  intro: "",
  count: 0,
  items: [],
  broken: [],
  policy_error: null,
  labels: {},
  notice_labels: {},
} as unknown as ChangesPayload;

function show(rules: ReviewRulesPayload) {
  vi.mocked(api.proposedDecisions).mockResolvedValue(decide);
  vi.mocked(api.changes).mockResolvedValue(changes);
  vi.mocked(api.reviewRules).mockResolvedValue(rules);
  const router = createMemoryRouter(
    [{ element: <Outlet context={{ refreshNav: vi.fn(), sync: {}, nav: null }} />, children: [{ path: "/decide", element: <Decide /> }] }],
    { initialEntries: ["/decide"] },
  );
  render(<RouterProvider router={router} />);
}

beforeEach(() => {
  vi.clearAllMocks();
  forgetReviewRules();
});

afterEach(cleanup);

describe("Decide review rules", () => {
  it("says there are none and how to add one", async () => {
    show({ rules: [], error: null });
    const section = await screen.findByTestId("review-rules");
    expect(within(section).getByText("No review rules: agent and person writes land directly.")).toBeTruthy();
    fireEvent.click(within(section).getByRole("button", { name: "How to add a rule" }));
    expect(section.querySelector("pre")?.textContent).toBe('[[review.rule]]\nwriter = "agent"\naction = "review"');
  });

  it("lists the rules in order", async () => {
    show({
      rules: [
        {
          number: 1,
          writer: "agent",
          project: "acme",
          folder: null,
          writes: "any",
          action: "review",
          description: "Rule 1: notes by agents in project acme wait for review in Decide.",
        },
        {
          number: 2,
          writer: "any",
          project: null,
          folder: "drafts",
          writes: "any",
          action: "direct",
          description: "Rule 2: notes by anyone in folder drafts are written directly.",
        },
      ],
      error: null,
    });
    const section = await screen.findByTestId("review-rules");
    expect(within(section).getByText("2 review rules apply.")).toBeTruthy();
    const items = within(within(section).getByRole("list", { name: "Review rules" })).getAllByRole("listitem");
    expect(items.map((item) => item.textContent)).toEqual([
      "Rule 1: notes by agents in project acme wait for review in Decide.",
      "Rule 2: notes by anyone in folder drafts are written directly.",
    ]);
  });
});
