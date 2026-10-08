import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { ConversationSummary } from "../../api/types";
import { ConversationList } from "./ConversationList";

const conversations: ConversationSummary[] = [
  { id: "c2", title: "What is meiosis?", created_at: "2026-10-08T10:00:00" },
  { id: "c1", title: "What is mitosis?", created_at: "2026-10-07T09:00:00" },
];

function renderList(overrides: Partial<Parameters<typeof ConversationList>[0]> = {}) {
  const props = {
    conversations,
    listError: null,
    activeId: null,
    onOpen: vi.fn(),
    onNewChat: vi.fn(),
    onDelete: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
  render(<ConversationList {...props} />);
  return props;
}

describe("ConversationList", () => {
  it("lists the conversations with their dates", () => {
    renderList();

    const meiosis = screen.getByRole("button", { name: /^What is meiosis\?/ });
    expect(meiosis).toHaveTextContent("2026");
    expect(screen.getByRole("button", { name: /^What is mitosis\?/ })).toBeInTheDocument();
  });

  it("marks the conversation on screen", () => {
    renderList({ activeId: "c1" });

    expect(screen.getByRole("button", { name: /^What is mitosis\?/ })).toHaveAttribute(
      "aria-current",
      "true",
    );
    expect(screen.getByRole("button", { name: /^What is meiosis\?/ })).not.toHaveAttribute(
      "aria-current",
    );
  });

  it("opens a conversation and starts a new chat", async () => {
    const props = renderList();

    await userEvent.click(screen.getByRole("button", { name: /^What is mitosis\?/ }));
    await userEvent.click(screen.getByRole("button", { name: "New chat" }));

    expect(props.onOpen).toHaveBeenCalledWith("c1");
    expect(props.onNewChat).toHaveBeenCalledTimes(1);
  });

  it("deletes only after the confirm click", async () => {
    const props = renderList();

    await userEvent.click(screen.getByRole("button", { name: "Delete What is mitosis?" }));
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(props.onDelete).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: "Delete What is mitosis?" }));
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(props.onDelete).toHaveBeenCalledWith("c1");
  });

  it("shows an empty state", () => {
    renderList({ conversations: [] });

    expect(screen.getByText(/No conversations yet/)).toBeInTheDocument();
  });

  it("shows a loading error", () => {
    renderList({ conversations: null, listError: "Cannot reach the StudyMate backend." });

    expect(screen.getByRole("alert")).toHaveTextContent("Could not load conversations");
  });
});
