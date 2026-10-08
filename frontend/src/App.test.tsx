import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import App from "./App";

/** Answer each backend path with a canned JSON body. */
function mockBackend(routes: Record<string, unknown>) {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => Promise.resolve(new Response(JSON.stringify(routes[url]), { status: 200 }))),
  );
}

describe("App smoke screen", () => {
  it("shows the backend as online and lists the documents", async () => {
    mockBackend({
      "/api/health": { status: "ok" },
      "/api/documents": [
        { id: "d1", filename: "biology.pdf", page_count: 12, chunk_count: 40, created_at: "2026-10-08T10:00:00" },
      ],
    });

    render(<App />);

    expect(await screen.findByText("online")).toBeInTheDocument();
    expect(await screen.findByText("biology.pdf (12 pages)")).toBeInTheDocument();
  });

  it("shows the backend as offline when /health cannot be reached", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    render(<App />);

    expect(await screen.findByText("offline")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Cannot reach the StudyMate backend");
  });
});
