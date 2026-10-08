# Phase 5 request: conversation memory

Plan Phase 5 and wait for my OK. Do not write code yet.

## Requirements
- Tables `conversations` (id, title, created_at) and `messages` (id,
  conversation_id, role, content, sources as JSON, reason, created_at),
  created at startup like the existing tables.
- `POST /chat` gets an optional `conversation_id`. Without one it starts a
  new conversation. The response includes the `conversation_id`.
- New endpoints: `GET /conversations` (newest first),
  `GET /conversations/{id}` (messages with sources),
  `DELETE /conversations/{id}`.
- Query rewriting: when the conversation has history, call the LLM to rewrite
  the follow-up into a standalone question, using the last N messages
  (setting `history_window`, default 6). Skip the rewrite for the first
  question. If the rewrite fails (any LLMError), fall back to the original
  question and log it. Keep the rewrite prompt in `app/rag/prompts.py` and
  tell the model to output only the question.
- Retrieval uses the rewritten question. The answer prompt also gets the
  recent history, marked as conversation context, not instructions.
- Return the rewritten question in the response so it can be evaluated.
- Title = the first question, shortened.
- Unknown `conversation_id` returns 404.
- Do not log question or answer text.

## Tests (FakeLLMClient only)
- A follow-up gets rewritten, and retrieval uses the rewritten text.
- The first question does not call the rewrite.
- A rewrite failure falls back to the original question.
- The history window is respected.
- Unknown conversation id returns 404.
- Deleting a conversation removes its messages.

## Out of scope
Streaming, summaries of old turns.

Never open .env. Follow CLAUDE.md.