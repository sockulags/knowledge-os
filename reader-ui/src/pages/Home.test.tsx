import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createMemoryRouter, Outlet, RouterProvider } from "react-router";
import type { HomePayload } from "../api/types";
import { api } from "../api/client";
import { Home } from "./Home";

const newProject = vi.fn();

vi.mock("../api/client", () => ({
  api: { home: vi.fn(), workspace: vi.fn() },
}));
vi.mock("../components/Structure", () => ({ useStructure: () => ({ newProject }) }));

function home(projects: HomePayload["projects"]): HomePayload {
  return {
    title: "Home",
    subtitle: "No decision governs this workspace yet.",
    waiting_on_you: [],
    in_force: [],
    recently_changed: [],
    projects,
    sections: { waiting_on_you: "Waiting", in_force: "In force", recently_changed: "Recent", projects: "Projects" },
    decide_link: "Open",
  };
}

function show(payload: HomePayload) {
  vi.mocked(api.home).mockResolvedValue(payload);
  vi.mocked(api.workspace).mockReturnValue(new Promise(() => undefined));
  const router = createMemoryRouter(
    [{ element: <Outlet context={{ refreshNav: vi.fn(), sync: {}, nav: null }} />, children: [{ path: "/", element: <Home /> }] }],
    { initialEntries: ["/"] },
  );
  render(<RouterProvider router={router} />);
}

beforeEach(() => vi.clearAllMocks());
afterEach(cleanup);

describe("Home first steps", () => {
  it("shows a way to the first page in a knowledge base without projects", async () => {
    show(home([]));
    await screen.findByTestId("first-steps");

    fireEvent.click(screen.getByRole("button", { name: "Create a page" }));
    expect(newProject).toHaveBeenLastCalledWith({ thenNewPage: true });

    fireEvent.click(screen.getByRole("button", { name: "Create your first project" }));
    expect(newProject).toHaveBeenLastCalledWith();
  });

  it("leaves them out once there is a project", async () => {
    show(home([{ id: "alpha", title: "Alpha" }]));
    await screen.findByText("Alpha");
    expect(screen.queryByTestId("first-steps")).toBeNull();
  });
});
