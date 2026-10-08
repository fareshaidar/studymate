import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import App from "./App";
import type { ConversationDetail, DocumentInfo, Source } from "./api/types";
import { loadSelection, NEW_CONVERSATION_KEY, saveSelection } from "./lib/selection";

const biology: DocumentInfo = {
  id: "d1", filename: "biology.pdf", page_count: 12, chunk_count: 40, created_at: "2026-10-08T10:00:00",
};
const history: DocumentInfo = {
  id: "d2", filename: "history.pdf", page_count: 5, chunk_count: 15, created_at: "2026-10-07T10:00:00",
};

const oldSource: Source = {
  n: 1, document_id: "gone", filename: "old-notes.pdf", page: 2, snippet: "Plants make sugar.", score: 0.8, cited: true,
};

/** A saved conversation about photosynthesis, citing a PDF that was since deleted. */
const photosynthesis: ConversationDetail = {
  id: "c9",
  title: "What is photosynthesis?",
  created_at: "2026-10-06T10:00:00",
  messages: [
    { id: 1, role: "user", content: "What is photosynthesis?", sources: null, reason: null, created_at: "2026-10-06T10:00:00" },
    { id: 2, role: "assistant", content: "Plants make sugar from light [1].", sources: [oldSource], reason: "ok", created_at: "2026-10-06T10:00:01" },
  ],
};

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status });
}

/**
 * A tiny in-memory backend behind a mocked fetch: health, documents,
 * conversations and chat. A new chat is saved as conversation "c1".
 */
function fakeBackend(initialDocs: DocumentInfo[], initialConversations: ConversationDetail[] = []) {
  let docs = [...initialDocs];
  let conversations = [...initialConversations];
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    if (url === "/api/health") return json({ status: "ok" });
    if (url === "/api/documents" && method === "GET") return json(docs);
    if (url === "/api/conversations" && method === "GET") {
      return json(conversations.map(({ id, title, created_at }) => ({ id, title, created_at })));
    }
    if (url === "/api/chat" && method === "POST") {
      const body = JSON.parse(init?.body as string) as { question: string; conversation_id?: string };
      if (!body.conversation_id) {
        conversations = [
          { id: "c1", title: body.question, created_at: "2026-10-08T12:00:00", messages: [] },
          ...conversations,
        ];
      }
      return json({
        answer: "Mitosis.",
        found: true,
        reason: "ok",
        sources: [],
        conversation_id: body.conversation_id ?? "c1",
        rewritten_question: null,
      });
    }
    const documentMatch = /^\/api\/documents\/([^/]+)$/.exec(url);
    if (documentMatch && method === "DELETE") {
      docs = docs.filter((d) => d.id !== documentMatch[1]);
      return new Response(null, { status: 204 });
    }
    const conversationMatch = /^\/api\/conversations\/([^/]+)$/.exec(url);
    if (conversationMatch) {
      const found = conversations.find((c) => c.id === conversationMatch[1]);
      if (!found) return json({ detail: "Conversation not found." }, 404);
      if (method === "DELETE") {
        conversations = conversations.filter((c) => c !== found);
        return new Response(null, { status: 204 });
      }
      return json(found);
    }
    return json({ detail: "Not Found" }, 404);
  });
  vi.stubGlobal("fetch", fetchMock);
  return {
    /** Delete a conversation behind the app's back, like another browser tab would. */
    deleteElsewhere: (id: string) => {
      conversations = conversations.filter((c) => c.id !== id);
    },
  };
}

async function ask(question: string): Promise<void> {
  await userEvent.type(screen.getByLabelText("Your question"), `${question}{Enter}`);
}

describe("App", () => {
  it("loads and lists the documents", async () => {
    fakeBackend([biology, history]);

    render(<App />);

    expect(await screen.findByText("biology.pdf")).toBeInTheDocument();
    expect(screen.getByText("history.pdf")).toBeInTheDocument();
    expect(screen.getByText("Searching all documents")).toBeInTheDocument();
    expect(await screen.findByText(/No conversations yet/)).toBeInTheDocument();
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

  it("moves the selection to the conversation and lists it after the first answer", async () => {
    fakeBackend([biology, history]);
    render(<App />);
    await userEvent.click(await screen.findByRole("checkbox", { name: /biology\.pdf/ }));

    await ask("What is mitosis?");
    expect(await screen.findByText("Mitosis.")).toBeInTheDocument();

    expect(loadSelection("c1")).toEqual(["d1"]);
    expect(loadSelection(NEW_CONVERSATION_KEY)).toEqual([]);
    // Still ticked on screen, now read from the conversation's own key.
    expect(screen.getByRole("checkbox", { name: /biology\.pdf/ })).toBeChecked();
    const listed = await screen.findByRole("button", { name: /^What is mitosis\?/ });
    expect(listed).toHaveAttribute("aria-current", "true");
  });

  it("reopens a saved conversation with its messages and its own selection", async () => {
    fakeBackend([biology, history], [photosynthesis]);
    saveSelection("c9", ["d2"]);
    render(<App />);

    await userEvent.click(await screen.findByRole("button", { name: /^What is photosynthesis\?/ }));

    expect(await screen.findByText("Plants make sugar from light")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /history\.pdf/ })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: /biology\.pdf/ })).not.toBeChecked();
    // Its source's PDF no longer exists, so there is no broken link.
    expect(screen.getByText("(document deleted)")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Open PDF/ })).not.toBeInTheDocument();
  });

  it("goes back to a new chat after deleting the open conversation", async () => {
    fakeBackend([biology], [photosynthesis]);
    saveSelection("c9", ["d1"]);
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: /^What is photosynthesis\?/ }));
    await screen.findByText("Plants make sugar from light");

    await userEvent.click(screen.getByRole("button", { name: "Delete What is photosynthesis?" }));
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));

    expect(await screen.findByText("Ask a question about your documents.")).toBeInTheDocument();
    expect(await screen.findByText(/No conversations yet/)).toBeInTheDocument();
    expect(loadSelection("c9")).toEqual([]);
  });

  it("explains a conversation that was deleted elsewhere and refreshes the list", async () => {
    const backend = fakeBackend([biology], [photosynthesis]);
    render(<App />);
    const listed = await screen.findByRole("button", { name: /^What is photosynthesis\?/ });

    backend.deleteElsewhere("c9");
    await userEvent.click(listed);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Conversation not found.");
    expect(within(alert).getByRole("button", { name: "Start a new chat" })).toBeInTheDocument();
    expect(await screen.findByText(/No conversations yet/)).toBeInTheDocument();
  });

  it("shows the offline banner and list errors when the backend is down", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    render(<App />);

    expect(await screen.findByText(/backend is not responding/)).toBeInTheDocument();
    expect(await screen.findByText(/Could not load documents/)).toBeInTheDocument();
    expect(await screen.findByText(/Could not load conversations/)).toBeInTheDocument();
  });
});
