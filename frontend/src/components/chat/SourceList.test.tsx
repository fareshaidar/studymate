import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { Source } from "../../api/types";
import { SourceList } from "./SourceList";

function source(n: number, cited: boolean): Source {
  return {
    n,
    document_id: `d${n}`,
    filename: `file${n}.pdf`,
    page: n * 10,
    snippet: `snippet ${n}`,
    score: 0.7,
    cited,
  };
}

describe("SourceList", () => {
  it("shows cited sources in number order, with a link to each page", () => {
    render(<SourceList sources={[source(3, true), source(1, true)]} />);

    const links = screen.getAllByRole("link");
    expect(links.map((link) => link.getAttribute("href"))).toEqual([
      "/api/documents/d1/file#page=10",
      "/api/documents/d3/file#page=30",
    ]);
    expect(screen.queryByText(/Other retrieved passages/)).not.toBeInTheDocument();
  });

  it("folds the uncited passages away, with their count", () => {
    const { container } = render(
      <SourceList sources={[source(1, true), source(2, false), source(3, false)]} />,
    );

    expect(screen.getByText("Other retrieved passages (2)")).toBeInTheDocument();
    const details = container.querySelector("details");
    expect(details).not.toHaveAttribute("open");
    expect(details).toHaveTextContent("file2.pdf");
    expect(details).toHaveTextContent("file3.pdf");
    expect(details).not.toHaveTextContent("file1.pdf");
  });

  it("renders nothing when there are no sources", () => {
    const { container } = render(<SourceList sources={[]} />);

    expect(container).toBeEmptyDOMElement();
  });
});
