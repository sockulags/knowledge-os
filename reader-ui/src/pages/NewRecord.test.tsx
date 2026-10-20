import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, Outlet, RouterProvider } from "react-router";
import type { PageTemplate, TemplatesPayload } from "../api/types";
import { api } from "../api/client";
import { write } from "../api/write";
import { NewGeneralPage } from "./NewRecord";

vi.mock("../api/client", () => ({ api: { templates: vi.fn(), record: vi.fn() } }));
vi.mock("../api/write", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/write")>()),
  write: { create: vi.fn(), attach: vi.fn(), preview: vi.fn() },
}));

function template(name: string, kind: PageTemplate["kind"], body: string): PageTemplate {
  return { name, title: name, description: "", kind, body, source: "built-in", path: null, error: null };
}

const templates: TemplatesPayload = {
  templates: [template("blank", "note", ""), template("how-to", "note", "## Steps\n"), template("decision", "decision", "## Decision\n")],
  folder: "templates",
  language: {
    label: "Start from",
    hint: "",
    built_in: "Built in",
    own: "{path}",
    unusable: "{error}",
    replace_title: "Replace?",
    replace_body: "{title}",
    replace_confirm: "Replace",
    replace_cancel: "Keep",
  },
};

function renderAt(path: string) {
  const router = createMemoryRouter(
    [
      {
        path: "/",
        element: <Outlet context={{ refreshNav: vi.fn(), sync: {}, nav: null }} />,
        children: [
          { path: "new", element: <NewGeneralPage /> },
          { path: "r/:recordId", element: <p>The new page</p> },
        ],
      },
    ],
    { initialEntries: [path] },
  );
  render(<RouterProvider router={router} />);
}

beforeEach(() => {
  vi.mocked(api.templates).mockResolvedValue(templates);
  vi.mocked(write.create).mockResolvedValue({
    ok: true,
    data: {
      id: "team-glossary",
      status: "active",
      path: "memory/team-glossary.md",
      content_sha256: "sha",
      index: { refreshed: true, count: 1, error: null },
      commit: null,
    },
  } as never);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("NewGeneralPage", () => {
  it("creates a memory page outside any project", async () => {
    const user = userEvent.setup();
    renderAt("/new");

    expect(await screen.findByRole("heading", { name: "New general page" })).toBeTruthy();
    // Decisions belong to a project, so their template is not offered.
    await screen.findByRole("radio", { name: /how-to/ });
    expect(screen.queryByRole("radio", { name: /decision/ })).toBeNull();
    expect(screen.queryByLabelText(/^Folder/)).toBeNull();

    await user.type(screen.getByLabelText(/^Title/), "Team glossary");
    await user.click(screen.getByRole("radio", { name: "Memory" }));
    await user.type(screen.getByLabelText("Page text"), "Words we use.");
    await user.click(screen.getByRole("button", { name: "Create page" }));

    expect(await screen.findByText("The new page")).toBeTruthy();
    const request = vi.mocked(write.create).mock.calls[0][0];
    expect(request).not.toHaveProperty("project_path");
    expect(request.metadata).toMatchObject({
      id: "team-glossary",
      title: "Team glossary",
      type: "memory",
      status: "active",
      scope: "general",
    });
    expect(request.metadata).not.toHaveProperty("record_kind");
  });

  it("creates a knowledge page by default", async () => {
    const user = userEvent.setup();
    renderAt("/new");

    await user.type(await screen.findByLabelText(/^Title/), "Style guide");
    expect((screen.getByRole("radio", { name: "Knowledge" }) as HTMLInputElement).checked).toBe(true);
    await user.type(screen.getByLabelText("Page text"), "How we write.");
    await user.click(screen.getByRole("button", { name: "Create page" }));

    await waitFor(() => expect(write.create).toHaveBeenCalledTimes(1));
    expect(vi.mocked(write.create).mock.calls[0][0].metadata).toMatchObject({ type: "knowledge", scope: "general" });
  });
});
