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
      metadata: { title: "Note", description: "", tags: [], related: [], sources: [] },
      content_sha256: "sha-1",
      body_change_needs_confirmation: false,
      decision_actions: null,
      delete: null,
    },
  } as unknown as RecordPayload;
}

/** The page as another writer left it on disk. */
function theirs(): RecordPayload {
  const current = record();
  current.editing.raw_body = "Hello from the agent";
  current.editing.metadata = { title: "Note", description: "", tags: ["agent"], related: [], sources: [] } as never;
  current.editing.content_sha256 = "sha-theirs";
  return current;
}

const conflict = {
  ok: false as const,
  status: 409,
  failure: { error: "conflict", detail: "The file changed.", current_sha256: "sha-theirs" },
};

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

/** The quick-find index the pickers search. */
function entry(id: string, title: string) {
  return { id, title, kind: "knowledge", status_pill: null, project: null, group: "pages", kind_label: "Page" };
}
const nav = {
  record_index: [
    entry("note", "Note"),
    entry("style-guide", "Style guide"),
    entry("glossary", "Glossary"),
    { ...entry("writing", "Writing skill"), kind: "skill" },
  ],
};

function renderEditor(shellNav: unknown = null) {
  const router = createMemoryRouter(
    [
      {
        path: "/",
        element: <Outlet context={{ refreshNav: vi.fn(), sync: {}, nav: shellNav }} />,
        children: [
          { path: "r/:recordId/edit", element: <EditRecord /> },
          { path: "r/:recordId", element: <p>The page</p> },
        ],
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

  it("shows a conflict next to the current version and keeps the person's text on top of it", async () => {
    const user = userEvent.setup();
    vi.mocked(write.edit).mockResolvedValueOnce(conflict as never).mockResolvedValueOnce(written("sha-3") as never);
    renderEditor();

    const text = (await screen.findByLabelText("Page text")) as HTMLTextAreaElement;
    await user.type(text, " world");
    vi.mocked(api.record).mockResolvedValue(theirs());
    await user.click(saveButton());

    const heading = await screen.findByRole("heading", { name: "This page changed while you were editing" });
    expect(document.activeElement).toBe(heading.closest("section"));
    expect(screen.getByRole("heading", { name: "Current version" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Your text" })).toBeTruthy();
    expect(screen.getByText("Hello from the agent")).toBeTruthy();
    expect(screen.getByText(/Properties that also differ: tags/)).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Keep mine on top of the new version" }));
    await waitFor(() => expect(screen.getByText(/^Saved /)).toBeTruthy());
    // Against the new revision, with the person's text; their tag removal too.
    expect(write.edit).toHaveBeenLastCalledWith("note", {
      expected_sha256: "sha-theirs",
      metadata: { tags: null },
      body: "Hello world",
    });
    expect(screen.queryByRole("heading", { name: "This page changed while you were editing" })).toBeNull();
    expect(text.value).toBe("Hello world");
  });

  it("takes the current version into the editor", async () => {
    const user = userEvent.setup();
    vi.mocked(write.edit).mockResolvedValueOnce(conflict as never);
    renderEditor();

    const text = (await screen.findByLabelText("Page text")) as HTMLTextAreaElement;
    await user.type(text, " world");
    vi.mocked(api.record).mockResolvedValue(theirs());
    await user.click(saveButton());

    await user.click(await screen.findByRole("button", { name: "Take theirs" }));
    expect(text.value).toBe("Hello from the agent");
    expect((screen.getByLabelText(/^Tags/) as HTMLInputElement).value).toBe("agent");
    expect(screen.queryByText("Unsaved changes")).toBeNull();
    expect(saveButton().disabled).toBe(true);
    expect(write.edit).toHaveBeenCalledTimes(1);
  });

  it("falls back to a reload when the current version cannot be loaded", async () => {
    const user = userEvent.setup();
    vi.mocked(write.edit).mockResolvedValueOnce(conflict as never);
    renderEditor();

    const text = (await screen.findByLabelText("Page text")) as HTMLTextAreaElement;
    await user.type(text, " world");
    vi.mocked(api.record).mockRejectedValue(new Error("down"));
    await user.click(saveButton());

    expect(await screen.findByRole("button", { name: "Reload current version" })).toBeTruthy();
  });

  it("saves and then leaves from the unsaved-changes dialog", async () => {
    const user = userEvent.setup();
    vi.mocked(write.edit).mockResolvedValueOnce(written("sha-2") as never);
    renderEditor();

    const text = await screen.findByLabelText("Page text");
    await user.type(text, " world");
    await user.click(screen.getByRole("button", { name: "Close" }));
    await user.click(await screen.findByRole("button", { name: "Save and leave" }));

    expect(await screen.findByText("The page")).toBeTruthy();
    expect(write.edit).toHaveBeenCalledWith("note", { expected_sha256: "sha-1", body: "Hello world" });
  });

  it("stays in the editor with the conflict when Save and leave cannot save", async () => {
    const user = userEvent.setup();
    vi.mocked(write.edit).mockResolvedValueOnce(conflict as never);
    renderEditor();

    const text = (await screen.findByLabelText("Page text")) as HTMLTextAreaElement;
    await user.type(text, " world");
    vi.mocked(api.record).mockResolvedValue(theirs());
    await user.click(screen.getByRole("button", { name: "Close" }));
    await user.click(await screen.findByRole("button", { name: "Save and leave" }));

    expect(await screen.findByRole("heading", { name: "This page changed while you were editing" })).toBeTruthy();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.queryByText("The page")).toBeNull();
    expect(text.value).toBe("Hello world");
  });

  it("does not offer Save and leave while an attachment is still being stored", async () => {
    const user = userEvent.setup();
    vi.mocked(write.attach).mockReturnValueOnce(new Promise(() => undefined) as never);
    renderEditor();

    const text = (await screen.findByLabelText("Page text")) as HTMLTextAreaElement;
    const input = document.querySelector<HTMLInputElement>('input[type="file"]')!;
    fireEvent.change(input, { target: { files: [new File(["png"], "shot.png", { type: "image/png" })] } });
    await waitFor(() => expect(text.value).toContain("Attaching shot.png"));
    await user.click(screen.getByRole("button", { name: "Close" }));

    const saveAndLeave = (await screen.findByRole("button", { name: "Save and leave" })) as HTMLButtonElement;
    expect(saveAndLeave.disabled).toBe(true);
  });

  it("saves a changed description and removes an emptied one", async () => {
    const user = userEvent.setup();
    vi.mocked(write.edit).mockResolvedValueOnce(written("sha-2") as never).mockResolvedValueOnce(written("sha-3") as never);
    renderEditor();

    const description = (await screen.findByLabelText(/^Description/)) as HTMLTextAreaElement;
    await user.type(description, "  What this note covers. ");
    await user.click(saveButton());
    await waitFor(() => expect(screen.getByText(/^Saved /)).toBeTruthy());
    expect(write.edit).toHaveBeenCalledWith("note", {
      expected_sha256: "sha-1",
      metadata: { description: "What this note covers." },
    });

    await user.clear(description);
    await user.click(saveButton());
    await waitFor(() => expect(write.edit).toHaveBeenCalledTimes(2));
    expect(write.edit).toHaveBeenLastCalledWith("note", { expected_sha256: "sha-2", metadata: { description: null } });
  });

  it("picks related pages by title and saves their ids", async () => {
    const user = userEvent.setup();
    vi.mocked(write.edit).mockResolvedValueOnce(written("sha-2") as never);
    renderEditor(nav);

    const related = await screen.findByRole("combobox", { name: "Add to related pages" });
    await user.type(related, "sty");
    expect(screen.getByRole("option", { name: /Style guide/ })).toBeTruthy();
    await user.keyboard("{Enter}");
    expect(screen.getByRole("button", { name: "Remove Style guide" })).toBeTruthy();

    // Neither the page itself nor a skill is offered.
    await user.type(related, "no");
    expect(screen.queryByRole("option", { name: /^Note/ })).toBeNull();
    await user.clear(related);
    await user.type(related, "writ");
    expect(screen.queryByRole("option", { name: /Writing skill/ })).toBeNull();
    await user.clear(related);

    await user.type(screen.getByRole("combobox", { name: "Add to based on" }), "glos{Enter}");
    await user.click(saveButton());
    await waitFor(() => expect(write.edit).toHaveBeenCalledTimes(1));
    expect(write.edit).toHaveBeenCalledWith("note", {
      expected_sha256: "sha-1",
      metadata: { related: ["style-guide"], sources: ["glossary"] },
    });
  });

  it("marks an id no page has as an error before saving", async () => {
    const user = userEvent.setup();
    renderEditor(nav);

    const related = await screen.findByRole("combobox", { name: "Add to related pages" });
    await user.type(related, "no-such-page");
    await user.click(screen.getByRole("option", { name: "Use the id “no-such-page”" }));

    expect(screen.getByRole("alert").textContent).toContain("No page has the id “no-such-page”");
    expect(related.getAttribute("aria-invalid")).toBe("true");
    expect(write.edit).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Remove no-such-page" }));
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("flags a saved relation that no longer resolves once the pages are known", async () => {
    const stale = record();
    stale.editing.metadata = { title: "Note", description: "", tags: [], related: [], sources: ["gone-page"] } as never;
    vi.mocked(api.record).mockResolvedValue(stale);
    renderEditor(nav);

    expect((await screen.findByRole("alert")).textContent).toContain("“gone-page”");
  });
});
