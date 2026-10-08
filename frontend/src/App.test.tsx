import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import App from "./App";
import type { DocumentInfo } from "./api/types";
import { loadSelection, NEW_CONVERSATION_KEY } from "./lib/selection";

const biology: DocumentInfo = {
  id: "d1", filename: "biology.pdf", page_count: 12, chunk_count: 40, created_at: "2026-10-08T10:00:00",
};
const history: DocumentInfo = {
  id: "d2", filename: "history.pdf", page_count: 5, chunk_count: 15, created_at: "2026-10-07T10:00:00",
};

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status });
}

/** A tiny in-memory backend behind a mocked fetch: health, list and delete. */
function fakeBackend(initialDocs: DocumentInfo[]) {
  let docs = [...initialDocs];
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    if (url === "/api/health") return json({ status: "ok" });
    if (url === "/api/documents" && method === "GET") return json(docs);
    if (url === "/api/chat" && method === "POST") {
      return json({
        answer: "Mitosis.",
        found: true,
        reason: "ok",
        sources: [],
        conversation_id: "c1",
        rewritten_question: null,
      });
    }
    const match = /^\/api\/documents\/([^/]+)$/.exec(url);
    if (match && method === "DELETE") {
      docs = docs.filter((d) => d.id !== match[1]);
      return new Response(null, { status: 204 });
    }
    return json({ detail: "Not Found" }, 404);
  });
  vi.stubGlobal("fetch", fetchMock);
}

describe("App", () => {
  it("loads and lists the documents", async () => {
    fakeBackend([biology, history]);

    render(<App />);

    expect(await screen.findByText("biology.pdf")).toBeInTheDocument();
    expect(screen.getByText("history.pdf")).toBeInTheDocument();
    expect(screen.getByText("Searching all documents")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("saves the selection and restores it after a reload", async () => {
    fakeBackend([biology, history]);
    const { unmount } = render(<App />);

    await userEvent.click(await screen.findByRole("checkbox", { name: /biology\.pdf/ }));
    expect(screen.getByText("Searching 1 of 2 documents")).toBeInTheDocument();
    expect(loadSelection(NEW_CONVERSATION_KEY)).toEqual(["d1"]);

    unmount(); // like closing the page
    render(<App />);

    expect(await screen.findByRole("checkbox", { name: /biology\.pdf/ })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: /history\.pdf/ })).not.toBeChecked();
  });

  it("drops a deleted document from the selection", async () => {
    fakeBackend([biology, history]);
    render(<App />);
    await userEvent.click(await screen.findByRole("checkbox", { name: /biology\.pdf/ }));

    await userEvent.click(screen.getByRole("button", { name: "Delete biology.pdf" }));
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));

    expect(await screen.findByText("Searching all documents")).toBeInTheDocument();
    expect(screen.queryByText("biology.pdf")).not.toBeInTheDocument();
  });

  it("moves the selection to the conversation once the first answer arrives", async () => {
    fakeBackend([biology, history]);
    render(<App />);
    await userEvent.click(await screen.findByRole("checkbox", { name: /biology\.pdf/ }));

    await userEvent.type(screen.getByLabelText("Your question"), "What is mitosis?{Enter}");
    expect(await screen.findByText("Mitosis.")).toBeInTheDocument();

    expect(loadSelection("c1")).toEqual(["d1"]);
    expect(loadSelection(NEW_CONVERSATION_KEY)).toEqual([]);
    // Still ticked on screen, now read from the conversation's own key.
    expect(screen.getByRole("checkbox", { name: /biology\.pdf/ })).toBeChecked();
  });

  it("shows the offline banner and a list error when the backend is down", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    render(<App />);

    expect(await screen.findByText(/backend is not responding/)).toBeInTheDocument();
    expect(await screen.findByText(/Could not load documents/)).toBeInTheDocument();
  });
});
