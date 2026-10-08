import { request } from "./client";
import type { ChatResponse } from "./types";

export interface ChatInput {
  question: string;
  /** Ticked documents; empty means "search all documents". */
  documentIds: string[];
  /** null starts a new conversation; an id continues that one. */
  conversationId: string | null;
}

/** POST /chat: answer a question from the documents, inside a conversation. */
export function sendChat({ question, documentIds, conversationId }: ChatInput): Promise<ChatResponse> {
  // Optional fields are left out rather than sent empty, matching the backend's
  // "missing means all documents / a new conversation".
  const body: Record<string, unknown> = { question };
  if (documentIds.length > 0) {
    body.document_ids = documentIds;
  }
  if (conversationId !== null) {
    body.conversation_id = conversationId;
  }
  return request<ChatResponse>("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}
