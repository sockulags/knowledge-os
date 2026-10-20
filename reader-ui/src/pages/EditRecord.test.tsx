import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, Outlet, RouterProvider } from "react-router";
import type { RecordPayload } from "../api/types";
import { api } from "../api/client";
import { write } from "../api/write";
import { EditRecord } from "./EditRecord";

vi.mock("../api/client", () => ({ api: { record: vi.fn() } }));
vi.mock("../api/write", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/write")>()),
  write: { edit: vi.fn(), attach: vi.fn(), preview: vi.fn() },
}));

/** A promise the test settles by hand, to hold a request in flight. */
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => (resolve = done));
  return { promise, resolve };
}

function record(): RecordPayload {
  return {
    id: "note",
    title: "Note",
    breadcrumb: [],
    editing: {
      editable: true,
      path: "projects/demo/note.md",
      project_id: "demo",
      folder: "",
      raw_body: "Hello",
      metadata: { title: "Note", tags: [], related: [], sources: [] },
      content_sha256: "sha-1",
      body_change_needs_confirmation: false,
      decision_actions: null,
      delete: null,
    },
  } as unknown as RecordPayload;
}

function written(sha: string) {
  return {
    ok: true as const,
    data: {
      id: "note",
      status: "accepted",
      path: "projects/demo/note.md",
      content_sha256: sha,
      index: { refreshed: true, count: 1, error: null },
      commit: null,
    },
  };
}

function renderEditor() {
  const router = createMemoryRouter(
    [
      {
        path: "/",
        element: <Outlet context={{ refreshNav: vi.fn(), sync: {}, nav: null }} />,
        children: [{ path: "r/:recordId/edit", element: <EditRecord /> }],
      },
    ],
    { initialEntries: ["/r/note/edit"] },
  );
  render(<RouterProvider router={router} />);
}

const saveButton = () => screen.getByRole("button", { name: "Save" }) as HTMLButtonElement;

beforeEach(() => {
  vi.mocked(api.record).mockResolvedValue(record());
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("EditRecord", () => {
  it("keeps text typed while a save is in flight and shows it as unsaved", async () => {
    const user = userEvent.setup();
    const pending = deferred<ReturnType<typeof written>>();
    vi.mocked(write.edit).mockReturnValueOnce(pending.promise as never);
    renderEditor();

    const text = (await screen.findByLabelText("Page text")) as HTMLTextAreaElement;
    await user.type(text, " world");
    await user.click(saveButton());
    expect(screen.getByText("Saving…")).toBeTruthy();

    await user.type(text, " again");
    pending.resolve(written("sha-2"));

    await waitFor(() => expect(screen.getByText("Unsaved changes")).toBeTruthy());
    expect(text.value).toBe("Hello world again");
    expect(write.edit).toHaveBeenCalledWith("note", { expected_sha256: "sha-1", body: "Hello world" });

    // The next save sends the rest, against the revision the first one wrote.
    vi.mocked(write.edit).mockResolvedValueOnce(written("sha-3") as never);
    await user.click(saveButton());
    await waitFor(() => expect(screen.getByText(/^Saved /)).toBeTruthy());
    expect(write.edit).toHaveBeenLastCalledWith("note", { expected_sha256: "sha-2", body: "Hello world again" });
    expect(saveButton().disabled).toBe(true);
  });

  it("does not save while an attachment is still being stored", async () => {
    const user = userEvent.setup();
    const upload = deferred<{ ok: true; data: { markdown: string } }>();
    vi.mocked(write.attach).mockReturnValueOnce(upload.promise as never);
    vi.mocked(write.edit).mockResolvedValue(written("sha-2") as never);
    renderEditor();

    const text = (await screen.findByLabelText("Page text")) as HTMLTextAreaElement;
    const input = document.querySelector<HTMLInputElement>('input[type="file"]')!;
    fireEvent.change(input, { target: { files: [new File(["png"], "shot.png", { type: "image/png" })] } });

    await waitFor(() => expect(text.value).toContain("[Attaching shot.png…]()"));
    expect(saveButton().disabled).toBe(true);
    await user.keyboard("{Control>}s{/Control}");
    expect(write.edit).not.toHaveBeenCalled();

    upload.resolve({ ok: true, data: { markdown: "![shot](assets/shot.png)" } });
    await waitFor(() => expect(saveButton().disabled).toBe(false));
    expect(text.value).toContain("![shot](assets/shot.png)");
    await user.keyboard("{Control>}s{/Control}");
    await waitFor(() => expect(write.edit).toHaveBeenCalledTimes(1));
    expect(vi.mocked(write.edit).mock.calls[0][1].body).not.toContain("Attaching");
  });
});
