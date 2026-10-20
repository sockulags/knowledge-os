import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useEffect, useState } from "react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { sync } from "../api/write";
import { usePageReload } from "./usePageReload";
import { useSync } from "./useSync";
import { useUnsavedChanges } from "./useUnsavedChanges";

vi.mock("../api/client", () => ({ api: { syncStatus: vi.fn(() => new Promise(() => undefined)) } }));
vi.mock("../api/write", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/write")>()),
  sync: { run: vi.fn() },
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

let mounts = 0;

/** Stands in for the editor: text from disk, dirty once it differs. */
function Page() {
  const [text, setText] = useState("from disk");
  useUnsavedChanges(text !== "from disk");
  useEffect(() => {
    mounts += 1;
  }, []);
  return <textarea aria-label="Page text" value={text} onChange={(event) => setText(event.target.value)} />;
}

/** The part of the shell that reloads the page after a sync pulled changes. */
function ShellPart() {
  const reload = usePageReload();
  const state = useSync(reload.request);
  return (
    <>
      <button type="button" onClick={() => void state.run()}>
        Sync
      </button>
      {reload.waiting && <p role="status">Reload waiting</p>}
      <main key={reload.version}>
        <Page />
      </main>
    </>
  );
}

function renderShell() {
  const router = createMemoryRouter([{ path: "/", element: <ShellPart /> }]);
  render(<RouterProvider router={router} />);
}

function pulled(count: number) {
  return {
    ok: true,
    data: { state: "synced", pulled: count, pushed: 0, reindexed: false, index_error: null, status: null },
  };
}

describe("usePageReload with a sync", () => {
  it("leaves unsaved text alone when a sync pulls, and reloads once it is saved", async () => {
    const user = userEvent.setup();
    mounts = 0;
    vi.mocked(sync.run).mockResolvedValue(pulled(2) as never);
    renderShell();

    const text = screen.getByLabelText("Page text") as HTMLTextAreaElement;
    await user.type(text, " and typed");
    await user.click(screen.getByRole("button", { name: "Sync" }));

    await waitFor(() => expect(screen.getByRole("status").textContent).toBe("Reload waiting"));
    expect((screen.getByLabelText("Page text") as HTMLTextAreaElement).value).toBe("from disk and typed");
    expect(mounts).toBe(1);

    // Saving (here: back to what is on disk) lets the waiting reload run.
    await user.clear(text);
    await user.type(text, "from disk");
    await waitFor(() => expect(mounts).toBe(2));
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("reloads at once when nothing is unsaved", async () => {
    const user = userEvent.setup();
    mounts = 0;
    vi.mocked(sync.run).mockResolvedValue(pulled(1) as never);
    renderShell();

    await user.click(screen.getByRole("button", { name: "Sync" }));
    await waitFor(() => expect(mounts).toBe(2));
    expect(screen.queryByRole("status")).toBeNull();
  });
});
