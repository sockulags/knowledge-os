import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { write } from "../api/write";
import { MarkdownEditor } from "./MarkdownEditor";

vi.mock("../api/write", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/write")>()),
  write: { attach: vi.fn(), preview: vi.fn() },
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function Harness({ onUploadingChange }: { onUploadingChange: (uploading: boolean) => void }) {
  const [value, setValue] = useState("Text");
  return (
    <MarkdownEditor
      value={value}
      onChange={setValue}
      attachTo={{ record_id: "note" }}
      onUploadingChange={onUploadingChange}
    />
  );
}

describe("MarkdownEditor", () => {
  it("reports an upload in progress until the file is stored", async () => {
    let finish!: (outcome: unknown) => void;
    vi.mocked(write.attach).mockReturnValueOnce(new Promise((done) => (finish = done)) as never);
    const onUploadingChange = vi.fn();
    render(<Harness onUploadingChange={onUploadingChange} />);
    expect(onUploadingChange).toHaveBeenLastCalledWith(false);

    const input = document.querySelector<HTMLInputElement>('input[type="file"]')!;
    fireEvent.change(input, { target: { files: [new File(["png"], "shot.png", { type: "image/png" })] } });

    await waitFor(() => expect(onUploadingChange).toHaveBeenLastCalledWith(true));
    expect(screen.getByText("Attaching…")).toBeTruthy();

    finish({ ok: true, data: { markdown: "![shot](assets/shot.png)" } });
    await waitFor(() => expect(onUploadingChange).toHaveBeenLastCalledWith(false));
    expect((screen.getByLabelText("Page text") as HTMLTextAreaElement).value).toContain("![shot](assets/shot.png)");
  });
});
