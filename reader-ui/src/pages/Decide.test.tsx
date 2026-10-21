import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { createMemoryRouter, Outlet, RouterProvider } from "react-router";
import type { ChangesPayload, DecidePayload, PendingObservationsPayload, ReviewRulesPayload } from "../api/types";
import { api } from "../api/client";
import { forgetReviewRules } from "../components/ReviewRules";
import { Decide } from "./Decide";

vi.mock("../api/client", () => ({
  api: { proposedDecisions: vi.fn(), changes: vi.fn(), reviewRules: vi.fn(), pendingObservations: vi.fn() },
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
  empty: { title: "Nothing to decide", title_observations: "No decisions or changes are waiting", body: "All clear." },
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

const noObservations = {
  heading: "Observations waiting",
  intro: "Not knowledge until reviewed.",
  count: 0,
  count_label: null,
  error: null,
  items: [],
  labels: {},
  notice_labels: {},
} as unknown as PendingObservationsPayload;

let observations: PendingObservationsPayload = noObservations;

const labels = {
  related: "Pages it may overlap with",
  no_related: "No page it may overlap with was found.",
  packet: "Review packet",
  agent: "Ask your agent",
  commands: "Or run one of these",
  copy: "Copy",
  copied: "Copied",
};

function reviewFields(id: string, title: string, related: boolean) {
  return {
    content_sha256: "a".repeat(64),
    scope: "project:demo",
    actions: {
      retain: true,
      promote: { target_id: id, title, acknowledge_related: related, allow_scope_broadening: true },
    },
  };
}

const twoObservations: PendingObservationsPayload = {
  ...noObservations,
  count: 2,
  count_label: "2 observations are waiting for review.",
  labels,
  items: [
    {
      id: "friday-deploys",
      title: "Deploys fail on Fridays",
      excerpt: "Friday deploys failed twice.",
      project: { id: "demo", title: "Demo" },
      proposed_by: { source: "other", label: "An agent run" },
      proposed_display: "2 days ago",
      proposed_exact: "10 September 2026",
      trust: "Observation — not knowledge",
      status_pill: null,
      related: [{ id: "deploy-freeze", title: "Deploy freeze on Fridays", reasons: ["FTS"], exists: true }],
      packet_html: "<h1>Discovery review packet</h1><p>Friday deploys failed twice.</p>",
      agent_phrase: "Review the discovery friday-deploys in Knowledge OS.",
      commands: [
        { action: "retain", label: "Keep it", command: 'python -m knowledge_os --root "/w" discovery retain friday-deploys' },
        { action: "reject", label: "Dismiss it", command: 'python -m knowledge_os --root "/w" discovery reject friday-deploys --reason "<why>"' },
      ],
      ...reviewFields("friday-deploys", "Deploys fail on Fridays", true),
    },
    {
      id: "slow-tests",
      title: "Tests are slow",
      excerpt: "",
      project: { id: "demo", title: "Demo" },
      proposed_by: { source: "other", label: "An agent run" },
      proposed_display: null,
      proposed_exact: null,
      trust: "Observation — not knowledge",
      status_pill: null,
      related: [],
      packet_html: "<p>Packet</p>",
      agent_phrase: "Review the discovery slow-tests in Knowledge OS.",
      commands: [],
      ...reviewFields("slow-tests", "Tests are slow", false),
    },
  ],
};

function show(rules: ReviewRulesPayload) {
  vi.mocked(api.proposedDecisions).mockResolvedValue(decide);
  vi.mocked(api.changes).mockResolvedValue(changes);
  vi.mocked(api.reviewRules).mockResolvedValue(rules);
  vi.mocked(api.pendingObservations).mockResolvedValue(observations);
  const router = createMemoryRouter(
    [{ element: <Outlet context={{ refreshNav: vi.fn(), sync: {}, nav: null }} />, children: [{ path: "/decide", element: <Decide /> }] }],
    { initialEntries: ["/decide"] },
  );
  render(<RouterProvider router={router} />);
}

beforeEach(() => {
  vi.clearAllMocks();
  forgetReviewRules();
  observations = noObservations;
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

describe("Decide observations waiting", () => {
  it("shows nothing when no observation waits", async () => {
    show({ rules: [], error: null });
    await screen.findByTestId("review-rules");
    expect(api.pendingObservations).toHaveBeenCalled();
    expect(screen.queryByTestId("pending-observations")).toBeNull();
    expect(screen.getByText("Nothing to decide")).toBeTruthy();
  });

  it("does not say nothing waits while observations do", async () => {
    observations = twoObservations;
    show({ rules: [], error: null });
    await screen.findByTestId("pending-observations");
    // The title follows the observation count once the page has caught up
    // with it, which can be a render after the section itself appears.
    expect(await screen.findByText("No decisions or changes are waiting")).toBeTruthy();
    expect(screen.queryByText("Nothing to decide")).toBeNull();
  });

  it("shows the count, the trust label, related pages, and the review packet", async () => {
    observations = twoObservations;
    show({ rules: [], error: null });
    const section = await screen.findByTestId("pending-observations");
    expect(within(section).getByText("2 observations are waiting for review.")).toBeTruthy();
    const rows = within(section).getAllByTestId("observation-row");
    expect(rows).toHaveLength(2);
    const first = rows[0];
    expect(within(first).getByText("Observation — not knowledge")).toBeTruthy();
    expect(within(first).getByRole("link", { name: "Deploy freeze on Fridays" }).getAttribute("href")).toBe("/r/deploy-freeze");
    expect(within(rows[1]).getByText("No page it may overlap with was found.")).toBeTruthy();
    expect(within(first).queryByTestId("observation-packet")).toBeNull();
    fireEvent.click(within(first).getByRole("button", { name: "Review packet" }));
    expect(within(first).getByTestId("observation-packet").textContent).toContain("Discovery review packet");
    expect(within(first).getByText('python -m knowledge_os --root "/w" discovery retain friday-deploys')).toBeTruthy();
    expect(within(first).getByText("Review the discovery friday-deploys in Knowledge OS.")).toBeTruthy();
  });

  it("copies a command, falling back when the clipboard API is missing", async () => {
    observations = twoObservations;
    const original = Object.getOwnPropertyDescriptor(navigator, "clipboard");
    Object.defineProperty(navigator, "clipboard", { value: undefined, configurable: true });
    const execCommand = vi.fn(() => true);
    Object.defineProperty(document, "execCommand", { value: execCommand, configurable: true });
    try {
      show({ rules: [], error: null });
      const section = await screen.findByTestId("pending-observations");
      const first = within(section).getAllByTestId("observation-row")[0];
      fireEvent.click(within(first).getAllByRole("button", { name: "Copy" })[0]);
      expect(await within(first).findByRole("button", { name: "Copied" })).toBeTruthy();
      expect(execCommand).toHaveBeenCalledWith("copy");
    } finally {
      if (original) Object.defineProperty(navigator, "clipboard", original);
      else delete (navigator as { clipboard?: unknown }).clipboard;
    }
  });
});
