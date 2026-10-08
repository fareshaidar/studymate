import { describe, expect, it, vi } from "vitest";

import { getFlashcards, getQuiz, getSummary } from "./study";

/** Mock fetch and return a function that reads the URL and JSON body of the first call. */
function captureRequest() {
  const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);
  return () => {
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.method).toBe("POST");
    return { url, body: JSON.parse(init.body as string) as Record<string, unknown> };
  };
}

describe("study API", () => {
  it("asks for a summary of all documents without a topic", async () => {
    const sent = captureRequest();

    await getSummary({ documentIds: [], topic: "   " });

    expect(sent()).toEqual({ url: "/api/study/summary", body: { document_ids: [] } });
  });

  it("sends the trimmed topic and the ticked documents", async () => {
    const sent = captureRequest();

    await getSummary({ documentIds: ["d1"], topic: "  mitosis " });

    expect(sent().body).toEqual({ document_ids: ["d1"], topic: "mitosis" });
  });

  it("sends the number of quiz questions", async () => {
    const sent = captureRequest();

    await getQuiz({ documentIds: ["d1"], topic: "", numQuestions: 3 });

    expect(sent()).toEqual({
      url: "/api/study/quiz",
      body: { document_ids: ["d1"], num_questions: 3 },
    });
  });

  it("sends the number of flashcards", async () => {
    const sent = captureRequest();

    await getFlashcards({ documentIds: [], topic: "cells", numCards: 12 });

    expect(sent()).toEqual({
      url: "/api/study/flashcards",
      body: { document_ids: [], topic: "cells", num_cards: 12 },
    });
  });
});
