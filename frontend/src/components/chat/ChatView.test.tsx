import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { sendChat } from "../../api/chat";
import { ApiError, type ChatResponse } from "../../api/types";
import { ChatView } from "./ChatView";

vi.mock("../../api/chat", () => ({ sendChat: vi.fn() }));

function reply(overrides: Partial<ChatResponse> = {}): ChatResponse {
  return {
    answer: "Cells divide by mitosis [1].",
    found: true,
    reason: "ok",
    sources: [
      {
        n: 1,
        document_id: "d1",
        filename: "biology.pdf",
        page: 4,
        snippet: "Mitosis produces two identical cells.",
        score: 0.82,
        cited: true,
      },
    ],
    conversation_id: "c1",
    rewritten_question: null,
    ...overrides,
  };
}

/** ChatView with the conversation id held in state, the way App holds it. */
function Harness({ documentIds = [] as string[] }) {
  const [conversationId, setConversationId] = useState<string | null>(null);
  return (
    <ChatView
      documentIds={documentIds}
      conversationId={conversationId}
      onConversationStarted={setConversationId}
      onNewChat={vi.fn()}
    />
  );
}

async function ask(question: string): Promise<void> {
  await userEvent.type(screen.getByLabelText("Your question"), `${question}{Enter}`);
}

beforeEach(() => {
  vi.mocked(sendChat).mockReset();
});

describe("ChatView", () => {
  it("shows the question, a thinking indicator, then the cited answer", async () => {
    let answer: (value: ChatResponse) => void = () => {};
    vi.mocked(sendChat).mockReturnValue(new Promise((resolve) => (answer = resolve)));
    render(<Harness documentIds={["d1"]} />);

    await ask("What is mitosis?");

    expect(screen.getByText("What is mitosis?")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("StudyMate is thinking…");
    expect(screen.getByLabelText("Your question")).toBeDisabled();
    expect(sendChat).toHaveBeenCalledWith({
      question: "What is mitosis?",
      documentIds: ["d1"],
      conversationId: null,
    });

    await act(async () => answer(reply()));

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Source 1: biology.pdf, page 4" })).toBeInTheDocument();
    expect(screen.getByLabelText("Your question")).toBeEnabled();
  });

  it("sends the conversation id with a follow-up", async () => {
    vi.mocked(sendChat).mockResolvedValue(reply());
    render(<Harness />);

    await ask("What is mitosis?");
    await screen.findByRole("button", { name: /Source 1/ });
    await ask("And why?");

    expect(vi.mocked(sendChat).mock.calls[1][0]).toEqual({
      question: "And why?",
      documentIds: [],
      conversationId: "c1",
    });
  });

  it("shows what a rewritten follow-up searched for", async () => {
    vi.mocked(sendChat).mockResolvedValue(reply({ rewritten_question: "Why does mitosis happen?" }));
    render(<Harness />);

    await ask("Why?");

    expect(await screen.findByText("Searched as: Why does mitosis happen?")).toBeInTheDocument();
  });

  it("shows the not-found notice for an answer that was not found", async () => {
    vi.mocked(sendChat).mockResolvedValue(
      reply({ found: false, reason: "no_relevant_chunks", sources: [], answer: "I couldn't find this." }),
    );
    render(<Harness />);

    await ask("What is a black hole?");

    expect(await screen.findByText("Not found in your material")).toBeInTheDocument();
  });

  it("puts a failed question back in the box and retries it", async () => {
    vi.mocked(sendChat)
      .mockRejectedValueOnce(new ApiError(502, "The AI service failed. Please try again."))
      .mockResolvedValueOnce(reply());
    render(<Harness />);

    await ask("What is mitosis?");

    expect(await screen.findByRole("alert")).toHaveTextContent("The AI service failed.");
    // Not saved by the backend, so not shown as sent either.
    expect(screen.queryByText("What is mitosis?", { selector: "p" })).not.toBeInTheDocument();
    expect(screen.getByLabelText("Your question")).toHaveValue("What is mitosis?");

    await userEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByRole("button", { name: /Source 1/ })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByText("What is mitosis?", { selector: "p" })).toBeInTheDocument();
    expect(sendChat).toHaveBeenCalledTimes(2);
  });

  it("shows a reopened conversation and keeps it when sending more", async () => {
    vi.mocked(sendChat).mockResolvedValue(reply({ answer: "Because cells grow." }));
    render(
      <ChatView
        documentIds={[]}
        conversationId="c1"
        initialMessages={[
          { id: 1, role: "user", text: "What is mitosis?" },
          {
            id: 2,
            role: "assistant",
            answer: "Cell division [1].",
            found: true,
            reason: "ok",
            sources: reply().sources,
            rewrittenQuestion: null,
          },
        ]}
        onConversationStarted={vi.fn()}
        onNewChat={vi.fn()}
      />,
    );

    expect(screen.getByText("What is mitosis?")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Source 1/ })).toBeInTheDocument();

    await ask("Why?");

    expect(await screen.findByText("Because cells grow.")).toBeInTheDocument();
    // The old messages are still there next to the new ones.
    expect(screen.getByText("What is mitosis?")).toBeInTheDocument();
    expect(screen.getByText("Why?", { selector: "p" })).toBeInTheDocument();
    expect(vi.mocked(sendChat).mock.calls[0][0].conversationId).toBe("c1");
  });

  it("ignores an answer that arrives after the chat was closed", async () => {
    let answer: (value: ChatResponse) => void = () => {};
    vi.mocked(sendChat).mockReturnValue(new Promise((resolve) => (answer = resolve)));
    const onConversationStarted = vi.fn();
    const { unmount } = render(
      <ChatView
        documentIds={[]}
        conversationId={null}
        onConversationStarted={onConversationStarted}
        onNewChat={vi.fn()}
      />,
    );

    await ask("What is mitosis?");
    unmount(); // the user opened another chat
    await act(async () => answer(reply()));

    expect(onConversationStarted).not.toHaveBeenCalled();
  });

  it("shows the busy countdown on a 503", async () => {
    vi.mocked(sendChat).mockRejectedValue(new ApiError(503, "The model is busy.", 12));
    render(<Harness />);

    await ask("What is mitosis?");

    expect(await screen.findByText("Busy: try again in 12 s.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeDisabled();
  });
});
