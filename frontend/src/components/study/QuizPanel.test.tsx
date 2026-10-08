import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getQuiz } from "../../api/study";
import type { QuizResponse } from "../../api/types";
import { QuizPanel } from "./QuizPanel";

vi.mock("../../api/study", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/study")>()),
  getQuiz: vi.fn(),
}));

const quiz: QuizResponse = {
  found: true,
  message: null,
  questions: [
    {
      question: "What does mitosis produce?",
      options: ["Two identical cells", "Four different cells", "One cell", "Spores"],
      correct_index: 0,
      explanation: "Mitosis copies the cell once.",
      source: { document_id: "d1", filename: "biology.pdf", page: 4 },
    },
    {
      question: "Where does photosynthesis happen?",
      options: ["Nucleus", "Chloroplast", "Ribosome", "Wall"],
      correct_index: 1,
      explanation: "Chloroplasts hold chlorophyll.",
      source: { document_id: "d1", filename: "biology.pdf", page: 9 },
    },
  ],
};

/**
 * The card of one question: the fieldset (found by its legend) holds the
 * options; its parent also holds the Check button and the answer.
 */
function question(name: RegExp): HTMLElement {
  const card = screen.getByRole("group", { name }).parentElement;
  if (!card) {
    throw new Error("question card not found");
  }
  return card;
}

async function makeQuiz(): Promise<void> {
  await userEvent.click(screen.getByRole("button", { name: "Make quiz" }));
  await screen.findByRole("group", { name: /What does mitosis produce/ });
}

beforeEach(() => {
  vi.mocked(getQuiz).mockReset();
  vi.mocked(getQuiz).mockResolvedValue(quiz);
});

describe("QuizPanel", () => {
  it("sends the number of questions and the topic", async () => {
    render(<QuizPanel documentIds={["d1"]} />);
    const count = screen.getByLabelText("Questions");

    await userEvent.clear(count);
    await userEvent.type(count, "3");
    await userEvent.type(screen.getByLabelText("Topic (optional)"), "cells");
    await makeQuiz();

    expect(getQuiz).toHaveBeenCalledWith({ documentIds: ["d1"], topic: "cells", numQuestions: 3 });
  });

  it("lets the browser block a count above the limit", async () => {
    render(<QuizPanel documentIds={[]} />);
    const count = screen.getByLabelText("Questions");

    await userEvent.clear(count);
    await userEvent.type(count, "50");
    await userEvent.click(screen.getByRole("button", { name: "Make quiz" }));

    // max=10 makes the field invalid, so the form is not submitted.
    expect(count).toBeInvalid();
    expect(getQuiz).not.toHaveBeenCalled();
  });

  it("uses the default count when the field is left empty", async () => {
    render(<QuizPanel documentIds={[]} />);

    await userEvent.clear(screen.getByLabelText("Questions"));
    await makeQuiz();

    expect(vi.mocked(getQuiz).mock.calls[0][0].numQuestions).toBe(5);
  });

  it("enables Check only after an option is picked", async () => {
    render(<QuizPanel documentIds={[]} />);
    await makeQuiz();
    const first = question(/What does mitosis produce/);

    const check = within(first).getByRole("button", { name: "Check answer" });
    expect(check).toBeDisabled();

    await userEvent.click(within(first).getByLabelText("Spores"));
    expect(check).toBeEnabled();
  });

  it("marks a wrong choice and the correct answer, with explanation and source", async () => {
    render(<QuizPanel documentIds={[]} />);
    await makeQuiz();
    const first = question(/What does mitosis produce/);

    await userEvent.click(within(first).getByLabelText("Spores"));
    await userEvent.click(within(first).getByRole("button", { name: "Check answer" }));

    expect(within(first).getByText("Not quite.")).toBeInTheDocument();
    expect(within(first).getByText("✗ (your answer)")).toBeInTheDocument();
    expect(within(first).getByText("✓ (correct answer)")).toBeInTheDocument();
    expect(within(first).getByText("Mitosis copies the cell once.")).toBeInTheDocument();
    expect(within(first).getByRole("link", { name: "Open PDF at page 4" })).toHaveAttribute(
      "href",
      "/api/documents/d1/file#page=4",
    );
    // Locked after checking.
    expect(within(first).getByLabelText(/Two identical cells/)).toBeDisabled();
  });

  it("shows the score once every question is checked", async () => {
    render(<QuizPanel documentIds={[]} />);
    await makeQuiz();

    const first = question(/What does mitosis produce/);
    await userEvent.click(within(first).getByLabelText("Two identical cells"));
    await userEvent.click(within(first).getByRole("button", { name: "Check answer" }));
    expect(within(first).getByText("Correct!")).toBeInTheDocument();
    expect(screen.queryByText(/Score:/)).not.toBeInTheDocument();

    const second = question(/Where does photosynthesis happen/);
    await userEvent.click(within(second).getByLabelText("Nucleus"));
    await userEvent.click(within(second).getByRole("button", { name: "Check answer" }));

    expect(screen.getByText("Score: 1 of 2")).toBeInTheDocument();
  });

  it("shows the not-found notice", async () => {
    vi.mocked(getQuiz).mockResolvedValue({ found: false, message: "No usable material.", questions: [] });
    render(<QuizPanel documentIds={[]} />);

    await userEvent.click(screen.getByRole("button", { name: "Make quiz" }));

    expect(await screen.findByText("No usable material.")).toBeInTheDocument();
  });
});
