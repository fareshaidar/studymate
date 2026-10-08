import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { Source } from "../../api/types";
import { AnswerMessage } from "./AnswerMessage";

const sources: Source[] = [
  {
    n: 1,
    document_id: "d1",
    filename: "biology.pdf",
    page: 4,
    snippet: "Mitosis produces two identical cells.",
    score: 0.82,
    cited: true,
  },
  {
    n: 2,
    document_id: "d2",
    filename: "history.pdf",
    page: 9,
    snippet: "The treaty was signed in 1648.",
    score: 0.71,
    cited: false,
  },
];

function renderAnswer(answer = "Cells divide by mitosis [1]. Odd number [7].") {
  render(<AnswerMessage answer={answer} found reason="ok" sources={sources} />);
}

const chipName = "Source 1: biology.pdf, page 4";

describe("AnswerMessage", () => {
  it("renders citations as buttons with descriptive names", () => {
    renderAnswer();

    const chip = screen.getByRole("button", { name: chipName });
    expect(chip).toHaveTextContent("[1]");
    expect(chip).toHaveAttribute("aria-expanded", "false");
  });

  it("leaves a number without a source as plain text", () => {
    renderAnswer();

    expect(screen.getByText(/Odd number \[7\]\./)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Source 7/ })).not.toBeInTheDocument();
  });

  it("opens a card with the source and a link to the PDF page", async () => {
    renderAnswer();

    await userEvent.click(screen.getByRole("button", { name: chipName }));

    const card = screen.getByRole("region", { name: "Source 1" });
    expect(within(card).getByText("biology.pdf")).toBeInTheDocument();
    expect(within(card).getByText(", page 4")).toBeInTheDocument();
    expect(within(card).getByText(/Mitosis produces two identical cells/)).toBeInTheDocument();
    const link = within(card).getByRole("link", { name: "Open PDF at page 4" });
    expect(link).toHaveAttribute("href", "/api/documents/d1/file#page=4");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(screen.getByRole("button", { name: chipName })).toHaveAttribute("aria-expanded", "true");
  });

  it("closes the card when the chip is clicked again", async () => {
    renderAnswer();
    const chip = screen.getByRole("button", { name: chipName });

    await userEvent.click(chip);
    await userEvent.click(chip);

    expect(screen.queryByRole("region", { name: "Source 1" })).not.toBeInTheDocument();
  });

  it("closes the card with Escape and with the close button", async () => {
    renderAnswer();

    await userEvent.click(screen.getByRole("button", { name: chipName }));
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("region", { name: "Source 1" })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: chipName }));
    await userEvent.click(screen.getByRole("button", { name: "Close source" }));
    expect(screen.queryByRole("region", { name: "Source 1" })).not.toBeInTheDocument();
  });

  it("shows the sources under the answer", () => {
    renderAnswer();

    expect(screen.getByText("Sources")).toBeInTheDocument();
    expect(screen.getByText("Other retrieved passages (1)")).toBeInTheDocument();
  });

  it("shows the not-found notice instead of the answer", () => {
    render(
      <AnswerMessage
        answer="I couldn't find this in your documents."
        found={false}
        reason="no_relevant_chunks"
        sources={[]}
      />,
    );

    expect(screen.getByText("Not found in your material")).toBeInTheDocument();
    expect(screen.queryByText("I couldn't find this in your documents.")).not.toBeInTheDocument();
  });
});
