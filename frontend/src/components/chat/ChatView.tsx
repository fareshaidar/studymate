import { useEffect, useRef, useState } from "react";

import { sendChat } from "../../api/chat";
import { ApiError, type ChatResponse } from "../../api/types";
import { ErrorNotice } from "../common/ErrorNotice";
import { MessageInput } from "./MessageInput";
import { MessageList, type ChatMessage } from "./MessageList";

interface ChatViewProps {
  /** Ticked documents; empty means "search all documents". */
  documentIds: string[];
  /** null until the first answer creates the conversation. */
  conversationId: string | null;
  /** The saved messages of a reopened conversation; read only when the chat is created. */
  initialMessages?: ChatMessage[];
  /** Ids of documents that still exist; see SourceDetails. */
  existingDocumentIds?: Set<string>;
  /** Called once, with the id the backend gave the new conversation. */
  onConversationStarted: (id: string) => void;
  onNewChat: () => void;
}

/** A failed send: what went wrong and the question to retry. */
interface FailedSend {
  id: number; // used as ErrorNotice's key, so each error gets a fresh countdown
  error: ApiError;
  question: string;
}

/**
 * The chat: the messages, the thinking indicator, errors and the input box.
 *
 * The backend saves nothing when a request fails, so on an error the question
 * is taken out of the list and put back into the input box: the screen always
 * matches what is stored, and Retry simply sends it again.
 */
export function ChatView({
  documentIds,
  conversationId,
  initialMessages = [],
  existingDocumentIds,
  onConversationStarted,
  onNewChat,
}: ChatViewProps) {
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState(false);
  const [failed, setFailed] = useState<FailedSend | null>(null);
  // Ids for React keys; a ref because changing it shouldn't re-render. New ids
  // start above the saved messages' database ids, so keys never collide.
  const nextId = useRef(Math.max(0, ...initialMessages.map((m) => m.id)) + 1);
  // False once this chat is no longer on screen (another chat was opened).
  const showing = useRef(true);

  useEffect(() => {
    // Set in the effect, not only at creation: React's StrictMode (in dev) runs
    // effects, cleans up and runs them again, which would leave it false.
    showing.current = true;
    return () => {
      showing.current = false;
    };
  }, []);

  async function send(question: string): Promise<void> {
    const userMessage: ChatMessage = { id: nextId.current++, role: "user", text: question };
    setMessages((previous) => [...previous, userMessage]);
    setDraft("");
    setFailed(null);
    setPending(true);

    let reply: ChatResponse;
    try {
      reply = await sendChat({ question, documentIds, conversationId });
    } catch (err) {
      if (!showing.current) {
        return;
      }
      setMessages((previous) => previous.filter((m) => m.id !== userMessage.id));
      setDraft(question);
      const error = err instanceof ApiError ? err : new ApiError(0, "Something went wrong.");
      setFailed({ id: nextId.current++, error, question });
      setPending(false);
      return;
    }

    // The user opened another chat while this answer was loading: drop it, or
    // onConversationStarted would give the other chat this conversation's id.
    // (The backend has still saved it; it shows when this conversation is reopened.)
    if (!showing.current) {
      return;
    }
    setMessages((previous) => [...previous, toAssistantMessage(nextId.current++, reply)]);
    setPending(false);
    if (conversationId === null) {
      onConversationStarted(reply.conversation_id);
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      <div className="min-h-0 flex-1 overflow-y-auto">
        {messages.length === 0 && !pending ? (
          <p className="text-gray-600">Ask a question about your documents.</p>
        ) : (
          <MessageList
            messages={messages}
            pending={pending}
            existingDocumentIds={existingDocumentIds}
          />
        )}
      </div>
      {failed && (
        <ErrorNotice
          key={failed.id}
          error={failed.error}
          onRetry={() => void send(failed.question)}
          onNewChat={onNewChat}
        />
      )}
      <MessageInput value={draft} onChange={setDraft} onSend={(q) => void send(q)} disabled={pending} />
    </div>
  );
}

function toAssistantMessage(id: number, reply: ChatResponse): ChatMessage {
  return {
    id,
    role: "assistant",
    answer: reply.answer,
    found: reply.found,
    reason: reply.reason,
    sources: reply.sources,
    rewrittenQuestion: reply.rewritten_question,
  };
}
