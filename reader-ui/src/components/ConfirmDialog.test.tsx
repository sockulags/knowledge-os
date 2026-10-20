import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { createMemoryRouter, Link, Outlet, RouterProvider } from "react-router";
import { ConfirmDialog } from "./ConfirmDialog";
import { UnsavedChangesDialog, type LeaveSave } from "./EditorParts";
import { useUnsavedChanges } from "../hooks/useUnsavedChanges";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

/** A page with something before and after the button that opens the dialog. */
function Page() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button">Before</button>
      <button type="button" onClick={() => setOpen(true)}>
        Delete page
      </button>
      <button type="button">After</button>
      {open && (
        <ConfirmDialog title="Delete this page?" confirmLabel="Delete" tone="danger" onConfirm={() => setOpen(false)} onCancel={() => setOpen(false)}>
          <input aria-label="Reason" />
        </ConfirmDialog>
      )}
    </>
  );
}

describe("ConfirmDialog", () => {
  it("keeps Tab and Shift+Tab inside the dialog", async () => {
    const user = userEvent.setup();
    render(<Page />);
    await user.click(screen.getByRole("button", { name: "Delete page" }));

    const reason = screen.getByRole("textbox", { name: "Reason" });
    const cancel = screen.getByRole("button", { name: "Cancel" });
    const confirm = screen.getByRole("button", { name: "Delete" });
    expect(document.activeElement).toBe(reason);

    await user.tab();
    expect(document.activeElement).toBe(cancel);
    await user.tab();
    expect(document.activeElement).toBe(confirm);
    await user.tab();
    expect(document.activeElement).toBe(reason);
    await user.tab({ shift: true });
    expect(document.activeElement).toBe(confirm);
  });

  it("gives focus back to the button that opened it, after Escape or Cancel", async () => {
    const user = userEvent.setup();
    render(<Page />);
    const opener = screen.getByRole("button", { name: "Delete page" });

    await user.click(opener);
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(opener);

    await user.click(opener);
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(document.activeElement).toBe(opener);
  });
});

/** A stand-in editor: dirty once its text differs, with an optional save. */
function Editor({ save }: { save?: (text: string) => Promise<boolean> }) {
  const [text, setText] = useState("");
  const [saved, setSaved] = useState("");
  const { blocker } = useUnsavedChanges(text !== saved);
  const leave: LeaveSave | undefined = save && {
    canSave: text !== saved,
    save: async () => {
      const ok = await save(text);
      if (ok) setSaved(text);
      return ok;
    },
  };
  return (
    <>
      <textarea aria-label="Page text" value={text} onChange={(event) => setText(event.target.value)} />
      <Link to="/elsewhere">Elsewhere</Link>
      <UnsavedChangesDialog blocker={blocker} save={leave} />
    </>
  );
}

function renderEditor(save?: (text: string) => Promise<boolean>) {
  const router = createMemoryRouter(
    [
      {
        path: "/",
        element: <Outlet />,
        children: [
          { index: true, element: <Editor save={save} /> },
          { path: "elsewhere", element: <p>Somewhere else</p> },
        ],
      },
    ],
    { initialEntries: ["/"] },
  );
  render(<RouterProvider router={router} />);
}

describe("UnsavedChangesDialog", () => {
  it("cycles focus among its buttons and returns it to the link on Cancel", async () => {
    const user = userEvent.setup();
    renderEditor(vi.fn(async () => true));
    await user.type(screen.getByRole("textbox", { name: "Page text" }), "draft");
    const link = screen.getByRole("link", { name: "Elsewhere" });
    await user.click(link);

    await screen.findByRole("dialog", { name: "Leave without saving?" });
    const cancel = screen.getByRole("button", { name: "Cancel" });
    const discard = screen.getByRole("button", { name: "Discard changes" });
    const saveAndLeave = screen.getByRole("button", { name: "Save and leave" });
    expect(document.activeElement).toBe(cancel);
    await user.tab();
    expect(document.activeElement).toBe(discard);
    await user.tab();
    expect(document.activeElement).toBe(saveAndLeave);
    await user.tab();
    expect(document.activeElement).toBe(cancel);
    await user.tab({ shift: true });
    expect(document.activeElement).toBe(saveAndLeave);

    await user.keyboard("{Shift>}{Tab}{Tab}{/Shift}{Enter}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(link);
    expect(screen.queryByText("Somewhere else")).toBeNull();
  });

  it("saves, then goes where the person was going", async () => {
    const user = userEvent.setup();
    const save = vi.fn(async () => true);
    renderEditor(save);
    await user.type(screen.getByRole("textbox", { name: "Page text" }), "draft");
    await user.click(screen.getByRole("link", { name: "Elsewhere" }));

    await user.click(await screen.findByRole("button", { name: "Save and leave" }));
    expect(await screen.findByText("Somewhere else")).toBeTruthy();
    expect(save).toHaveBeenCalledWith("draft");
  });

  it("stays with the editor when the save fails", async () => {
    const user = userEvent.setup();
    renderEditor(vi.fn(async () => false));
    const text = screen.getByRole("textbox", { name: "Page text" });
    await user.type(text, "draft");
    await user.click(screen.getByRole("link", { name: "Elsewhere" }));

    await user.click(await screen.findByRole("button", { name: "Save and leave" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(screen.queryByText("Somewhere else")).toBeNull();
    expect((text as HTMLTextAreaElement).value).toBe("draft");
  });

  it("offers only Discard where the page has no save to offer", async () => {
    const user = userEvent.setup();
    renderEditor();
    await user.type(screen.getByRole("textbox", { name: "Page text" }), "draft");
    await user.click(screen.getByRole("link", { name: "Elsewhere" }));

    await screen.findByRole("dialog");
    expect(screen.queryByRole("button", { name: "Save and leave" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Discard changes" }));
    expect(await screen.findByText("Somewhere else")).toBeTruthy();
  });
});
