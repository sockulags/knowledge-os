import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router";
import { ReaderCommands } from "./ReaderCommands";

const newProject = vi.fn();
vi.mock("./Structure", () => ({ useStructure: () => ({ newProject }) }));

let send: (command: string) => void = () => undefined;

function Where() {
  return <p data-testid="where">{useLocation().pathname}</p>;
}

// A plain MemoryRouter: a data router's navigation trips over jsdom's AbortSignal.
function show(projectId: string | null | undefined) {
  render(
    <MemoryRouter initialEntries={["/"]}>
      <ReaderCommands projectId={projectId} onToggleAgent={() => undefined} />
      <Where />
    </MemoryRouter>,
  );
}

const where = () => screen.getByTestId("where").textContent;

beforeEach(() => {
  vi.clearAllMocks();
  (window as { kosDesktop?: unknown }).kosDesktop = {
    onReaderCommand: (callback: (command: string) => void) => {
      send = callback;
      return () => undefined;
    },
  };
});
afterEach(() => {
  cleanup();
  delete (window as { kosDesktop?: unknown }).kosDesktop;
});

describe("New Page from the desktop menu", () => {
  it("opens a new page in the project", () => {
    show("alpha");
    act(() => send("new-page"));
    expect(where()).toBe("/p/alpha/new");
    expect(newProject).not.toHaveBeenCalled();
  });

  it("asks for a project first when there is none", () => {
    show(null);
    act(() => send("new-page"));
    expect(newProject).toHaveBeenCalledWith({ thenNewPage: true });
    expect(where()).toBe("/");
  });

  it("waits until it is known whether there is a project", () => {
    show(undefined);
    act(() => send("new-page"));
    expect(newProject).not.toHaveBeenCalled();
  });
});
