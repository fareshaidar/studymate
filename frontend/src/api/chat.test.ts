import { describe, expect, it, vi } from "vitest";

import { sendChat } from "./chat";

const reply = {
  answer: "Mitosis [1].",
  found: true,
  reason: "ok",
  sources: [],
  conversation_id: "c1",
  rewritten_question: null,
};

/** Mock fetch and return a function that reads the JSON body of the first call. */
function captureBody() {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(reply), { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);
  return () => {
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/chat");
    expect(init.method).toBe("POST");
    return JSON.parse(init.body as string) as Record<string, unknown>;
  };
}

describe("sendChat", () => {
  it("starts a new conversation over all documents with just the question", async () => {
    const body = captureBody();

    await expect(
      sendChat({ question: "What is mitosis?", documentIds: [], conversationId: null }),
    ).resolves.toEqual(reply);

    expect(body()).toEqual({ question: "What is mitosis?" });
  });

  it("sends the ticked documents and the conversation id for a follow-up", async () => {
    const body = captureBody();

    await sendChat({ question: "And meiosis?", documentIds: ["d1", "d2"], conversationId: "c1" });

    expect(body()).toEqual({
      question: "And meiosis?",
      document_ids: ["d1", "d2"],
      conversation_id: "c1",
    });
  });
});
