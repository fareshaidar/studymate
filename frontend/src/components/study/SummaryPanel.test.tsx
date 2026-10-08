import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getSummary } from "../../api/study";
import { ApiError, type SummaryResponse } from "../../api/types";
import { SummaryPanel } from "./SummaryPanel";

// Keep the real limits, replace only the request.
vi.mock("../../api/study", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/study")>()),
  getSummary: vi.fn(),
}));

function summary(overrides: Partial<SummaryResponse> = {}): SummaryResponse {
  return {
    found: true,
    message: null,
    summary: "Cells divide by mitosis.\n- Two identical cells",
    truncated: false,
    llm_calls: 1,
    pages: [{ document_id: "d1", filename: "biology.pdf", pages: [4, 2, 3, 9] }],
    ...overrides,
  };
}

beforeEach(() => {
  vi.mocked(getSummary).mockReset();
});

describe("SummaryPanel", () => {
  it("shows a loading message, then the summary and its pages", async () => {
    let finish: (value: SummaryResponse) => void = () => {};
    vi.mocked(getSummary).mockReturnValue(new Promise((resolve) => (finish = resolve)));
    render(<SummaryPanel documentIds={["d1"]} />);

    await userEvent.type(screen.getByLabelText("Topic (optional)"), "mitosis");
    await userEvent.click(screen.getByRole("button", { name: "Summarise" }));

    expect(getSummary).toHaveBeenCalledWith({ documentIds: ["d1"], topic: "mitosis" });
    expect(screen.getByRole("status")).toHaveTextContent("Summarising…");
    expect(screen.getByRole("button", { name: "Summarise" })).toBeDisabled();

    await act(async () => finish(summary()));

    expect(screen.getByText(/Cells divide by mitosis\./)).toBeInTheDocument();
    expect(screen.getByText(/biology\.pdf, pages 2–4, 9/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open PDF" })).toHaveAttribute(
      "href",
      "/api/documents/d1/file#page=2",
    );
    expect(screen.queryByText(/Partial summary/)).not.toBeInTheDocument();
  });

  it("warns when the summary is partial", async () => {
    vi.mocked(getSummary).mockResolvedValue(summary({ truncated: true }));
    render(<SummaryPanel documentIds={[]} />);

    await userEvent.click(screen.getByRole("button", { name: "Summarise" }));

    expect(
      await screen.findByText(
        /Partial summary: part of the material was skipped to stay within the AI call or time limit\./,
      ),
    ).toBeInTheDocument();
  });

  it("shows the backend's message when nothing usable was found", async () => {
    vi.mocked(getSummary).mockResolvedValue(
      summary({ found: false, message: "I couldn't find usable material for this in your documents.", summary: "", pages: [] }),
    );
    render(<SummaryPanel documentIds={[]} />);

    await userEvent.click(screen.getByRole("button", { name: "Summarise" }));

    expect(await screen.findByText("Not found in your material")).toBeInTheDocument();
    expect(screen.getByText(/couldn't find usable material/)).toBeInTheDocument();
  });

  it("asks for the document list to be reloaded when documents are gone", async () => {
    vi.mocked(getSummary).mockRejectedValue(
      new ApiError(404, "One or more of the selected documents no longer exist.", undefined, "document_not_found"),
    );
    const onDocumentsMissing = vi.fn();
    render(<SummaryPanel documentIds={["gone"]} onDocumentsMissing={onDocumentsMissing} />);

    await userEvent.click(screen.getByRole("button", { name: "Summarise" }));

    expect(await screen.findByText(/document list has been refreshed/)).toBeInTheDocument();
    expect(onDocumentsMissing).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
  });

  it("offers Retry after a failure", async () => {
    vi.mocked(getSummary)
      .mockRejectedValueOnce(new ApiError(502, "The AI service failed."))
      .mockResolvedValueOnce(summary());
    render(<SummaryPanel documentIds={[]} />);

    await userEvent.click(screen.getByRole("button", { name: "Summarise" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The AI service failed.");

    await userEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByText(/Cells divide by mitosis\./)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
