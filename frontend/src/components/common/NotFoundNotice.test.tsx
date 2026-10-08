import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { NotFoundNotice } from "./NotFoundNotice";

describe("NotFoundNotice", () => {
  it("explains no_relevant_chunks in plain words", () => {
    render(<NotFoundNotice reason="no_relevant_chunks" />);

    expect(screen.getByText("Not found in your material")).toBeInTheDocument();
    expect(screen.getByText(/No passage in the selected documents/)).toBeInTheDocument();
    expect(screen.getByText(/Try rephrasing/)).toBeInTheDocument();
  });

  it("explains model_declined in plain words", () => {
    render(<NotFoundNotice reason="model_declined" />);

    expect(screen.getByText(/none of them contained the answer/)).toBeInTheDocument();
  });

  it("falls back to a generic line for a missing or unknown reason", () => {
    render(<NotFoundNotice reason={null} />);

    expect(screen.getByText("Your documents don't seem to cover this.")).toBeInTheDocument();
  });

  it("shows the backend's own message when given one", () => {
    render(<NotFoundNotice reason="no_relevant_chunks" message="No pages matched that topic." />);

    expect(screen.getByText("No pages matched that topic.")).toBeInTheDocument();
    expect(screen.queryByText(/No passage in the selected documents/)).not.toBeInTheDocument();
  });
});
