import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getFlashcards } from "../../api/study";
import type { FlashcardsResponse } from "../../api/types";
import { FlashcardsPanel } from "./FlashcardsPanel";

vi.mock("../../api/study", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/study")>()),
  getFlashcards: vi.fn(),
}));

const deck: FlashcardsResponse = {
  found: true,
  message: null,
  cards: [
    { front: "What is mitosis?", back: "Cell division into two identical cells.", source: { document_id: "d1", filename: "biology.pdf", page: 4 } },
    { front: "What is a chloroplast?", back: "Where photosynthesis happens.", source: { document_id: "d1", filename: "biology.pdf", page: 9 } },
  ],
};

/** The card: the only button with aria-pressed (its pressed state shows which side is up). */
function card(): HTMLElement {
  const found = screen.getAllByRole("button").find((button) => button.hasAttribute("aria-pressed"));
  if (!found) {
    throw new Error("no flashcard on screen");
  }
  return found;
}

async function makeCards(): Promise<void> {
  await userEvent.click(screen.getByRole("button", { name: "Make flashcards" }));
  await screen.findByText("Card 1 of 2 · click the card to flip it");
}

beforeEach(() => {
  vi.mocked(getFlashcards).mockReset();
  vi.mocked(getFlashcards).mockResolvedValue(deck);
});

describe("FlashcardsPanel", () => {
  it("sends the default number of cards", async () => {
    render(<FlashcardsPanel documentIds={["d1"]} />);

    await makeCards();

    expect(getFlashcards).toHaveBeenCalledWith({ documentIds: ["d1"], topic: "", numCards: 10 });
  });

  it("shows the question first and flips to the answer and its source", async () => {
    render(<FlashcardsPanel documentIds={[]} />);
    await makeCards();

    expect(card()).toHaveTextContent("What is mitosis?");
    expect(screen.queryByRole("link")).not.toBeInTheDocument();

    await userEvent.click(card());

    expect(card()).toHaveAttribute("aria-pressed", "true");
    expect(card()).toHaveTextContent("Cell division into two identical cells.");
    expect(screen.getByRole("link", { name: "Open PDF at page 4" })).toBeInTheDocument();
  });

  it("moves between cards, starting each on its question", async () => {
    render(<FlashcardsPanel documentIds={[]} />);
    await makeCards();
    const previous = screen.getByRole("button", { name: "Previous" });
    const next = screen.getByRole("button", { name: "Next" });
    expect(previous).toBeDisabled();

    await userEvent.click(card()); // flip the first card
    await userEvent.click(next);

    expect(screen.getByText("Card 2 of 2 · click the card to flip it")).toBeInTheDocument();
    expect(card()).toHaveTextContent("What is a chloroplast?");
    expect(next).toBeDisabled();

    await userEvent.click(previous);
    expect(card()).toHaveTextContent("What is mitosis?");
  });

  it("shows the not-found notice", async () => {
    vi.mocked(getFlashcards).mockResolvedValue({ found: false, message: "No usable material.", cards: [] });
    render(<FlashcardsPanel documentIds={[]} />);

    await userEvent.click(screen.getByRole("button", { name: "Make flashcards" }));

    expect(await screen.findByText("No usable material.")).toBeInTheDocument();
  });
});
