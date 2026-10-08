import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { DeleteWithConfirm } from "./DeleteWithConfirm";

function renderRow(onDelete = vi.fn().mockResolvedValue(undefined)) {
  render(
    <DeleteWithConfirm name="notes.pdf" onDelete={onDelete}>
      <span>notes.pdf</span>
    </DeleteWithConfirm>,
  );
  return onDelete;
}

describe("DeleteWithConfirm", () => {
  it("does not move focus when it first appears", () => {
    renderRow();

    expect(document.body).toHaveFocus();
  });

  it("moves focus to the confirm button, and back to Delete on Cancel", async () => {
    renderRow();

    await userEvent.click(screen.getByRole("button", { name: "Delete notes.pdf" }));
    expect(screen.getByRole("button", { name: "Delete" })).toHaveFocus();

    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("button", { name: "Delete notes.pdf" })).toHaveFocus();
  });

  it("can be used with the keyboard alone", async () => {
    const onDelete = renderRow();

    await userEvent.tab();
    expect(screen.getByRole("button", { name: "Delete notes.pdf" })).toHaveFocus();
    await userEvent.keyboard("{Enter}"); // open the confirm
    await userEvent.keyboard("{Enter}"); // confirm

    expect(onDelete).toHaveBeenCalledTimes(1);
  });
});
