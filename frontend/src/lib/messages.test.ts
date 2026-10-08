import { describe, expect, it } from "vitest";

import type { Source, StoredMessage } from "../api/types";
import { fromStoredMessages } from "./messages";

const source: Source = {
  n: 1,
  document_id: "d1",
  filename: "biology.pdf",
  page: 4,
  snippet: "Mitosis…",
  score: 0.8,
  cited: true,
};

function stored(overrides: Partial<StoredMessage>): StoredMessage {
  return {
    id: 1,
    role: "assistant",
    content: "text",
    sources: null,
    reason: null,
    created_at: "2026-10-08T10:00:00",
    ...overrides,
  };
}

describe("fromStoredMessages", () => {
  it("converts a question and its answer", () => {
    const messages = fromStoredMessages([
      stored({ id: 1, role: "user", content: "What is mitosis?" }),
      stored({ id: 2, content: "Cell division [1].", sources: [source], reason: "ok" }),
    ]);

    expect(messages).toEqual([
      { id: 1, role: "user", text: "What is mitosis?" },
      {
        id: 2,
        role: "assistant",
        answer: "Cell division [1].",
        found: true,
        reason: "ok",
        sources: [source],
        rewrittenQuestion: null,
      },
    ]);
  });

  it.each([
    ["ok", true],
    ["no_relevant_chunks", false],
    ["model_declined", false],
    [null, true],
  ])("derives found from reason %s", (reason, found) => {
    const [message] = fromStoredMessages([stored({ reason })]);

    expect(message).toMatchObject({ found });
  });

  it("turns missing sources into an empty list", () => {
    const [message] = fromStoredMessages([stored({ sources: null })]);

    expect(message).toMatchObject({ sources: [] });
  });
});
