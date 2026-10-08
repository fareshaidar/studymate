import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ApiError, type DocumentInfo } from "../../api/types";
import { DocumentList } from "./DocumentList";

const docs: DocumentInfo[] = [
  { id: "d1", filename: "biology.pdf", page_count: 12, chunk_count: 40, created_at: "2026-10-08T10:00:00" },
  { id: "d2", filename: "history.pdf", page_count: 1, chunk_count: 2, created_at: "2026-10-07T10:00:00" },
];

function renderList(overrides: Partial<Parameters<typeof DocumentList>[0]> = {}) {
  const props = {
    documents: docs,
    selectedIds: [],
    onSelectionChange: vi.fn(),
    onDelete: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
  render(<DocumentList {...props} />);
  return props;
}

describe("DocumentList", () => {
  it("shows each document with its page count", () => {
    renderList();

    expect(screen.getByText("biology.pdf")).toBeInTheDocument();
    expect(screen.getByText("12 pages")).toBeInTheDocument();
    expect(screen.getByText("1 page")).toBeInTheDocument();
  });

  it("shows an empty state when there are no documents", () => {
    renderList({ documents: [] });

    expect(screen.getByText(/No documents yet/)).toBeInTheDocument();
  });

  it("describes the search scope", () => {
    renderList();
    expect(screen.getByText("Searching all documents")).toBeInTheDocument();
  });

  it("counts the ticked documents in the scope line", () => {
    renderList({ selectedIds: ["d2"] });

    expect(screen.getByText("Searching 1 of 2 documents")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /history\.pdf/ })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: /biology\.pdf/ })).not.toBeChecked();
  });

  it("adds and removes ids when boxes are ticked", async () => {
    const props = renderList({ selectedIds: ["d2"] });

    await userEvent.click(screen.getByRole("checkbox", { name: /biology\.pdf/ }));
    expect(props.onSelectionChange).toHaveBeenLastCalledWith(["d2", "d1"]);

    await userEvent.click(screen.getByRole("checkbox", { name: /history\.pdf/ }));
    expect(props.onSelectionChange).toHaveBeenLastCalledWith([]);
  });

  it("deletes only after the confirm click", async () => {
    const props = renderList();

    await userEvent.click(screen.getByRole("button", { name: "Delete biology.pdf" }));
    expect(props.onDelete).not.toHaveBeenCalled();
    expect(screen.getByText("Delete biology.pdf?")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(props.onDelete).toHaveBeenCalledWith("d1");
  });

  it("does not delete when the confirm is cancelled", async () => {
    const props = renderList();

    await userEvent.click(screen.getByRole("button", { name: "Delete biology.pdf" }));
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(props.onDelete).not.toHaveBeenCalled();
    expect(screen.queryByText("Delete biology.pdf?")).not.toBeInTheDocument();
  });

  it("shows a failed delete on that row", async () => {
    renderList({ onDelete: vi.fn().mockRejectedValue(new ApiError(404, "Document not found.")) });

    await userEvent.click(screen.getByRole("button", { name: "Delete biology.pdf" }));
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Document not found.");
    // The row is back to its normal state, so the user can try again.
    expect(screen.getByRole("button", { name: "Delete biology.pdf" })).toBeInTheDocument();
  });
});
