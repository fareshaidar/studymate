import type { StoredMessage } from "../api/types";
import type { ChatMessage } from "../components/chat/MessageList";

/** The reasons for which an answer counts as "not found". */
const NOT_FOUND_REASONS = new Set(["no_relevant_chunks", "model_declined"]);

/**
 * Turn the saved messages of a conversation into what the chat shows.
 *
 * The backend stores `reason` but not `found`, so `found` is derived from it
 * (the same rule the backend uses: found means reason "ok"). An unknown or
 * missing reason still shows the saved text rather than hiding it. The
 * rewritten question isn't stored, so reopened answers have no "Searched as" line.
 */
export function fromStoredMessages(messages: StoredMessage[]): ChatMessage[] {
  return messages.map((message) =>
    message.role === "user"
      ? { id: message.id, role: "user", text: message.content }
      : {
          id: message.id,
          role: "assistant",
          answer: message.content,
          found: !NOT_FOUND_REASONS.has(message.reason ?? ""),
          reason: message.reason,
          sources: message.sources ?? [],
          rewrittenQuestion: null,
        },
  );
}
