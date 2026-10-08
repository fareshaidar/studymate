import { request } from "./client";
import type { ConversationDetail, ConversationSummary } from "./types";

/** GET /conversations: all conversations, newest first, without messages. */
export function listConversations(): Promise<ConversationSummary[]> {
  return request<ConversationSummary[]>("/conversations");
}

/** GET /conversations/{id}: one conversation with all its messages. */
export function getConversation(id: string): Promise<ConversationDetail> {
  return request<ConversationDetail>(`/conversations/${encodeURIComponent(id)}`);
}

/** DELETE /conversations/{id}: removes the conversation and its messages. */
export function deleteConversation(id: string): Promise<void> {
  return request<void>(`/conversations/${encodeURIComponent(id)}`, { method: "DELETE" });
}
