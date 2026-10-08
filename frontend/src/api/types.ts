/** Shapes of the backend's JSON responses (see backend/app/api/). */

export interface Health {
  status: string;
}

/** One uploaded PDF, as returned by GET/POST /documents. */
export interface DocumentInfo {
  id: string;
  filename: string;
  page_count: number;
  chunk_count: number;
  created_at: string; // ISO date-time string
}

/**
 * One passage shown to the model. `n` is the number used for [n] in the answer;
 * `page` starts at 1; `cited` says whether the answer actually cites it.
 */
export interface Source {
  n: number;
  document_id: string;
  filename: string;
  page: number;
  snippet: string;
  score: number;
  cited: boolean;
}

/** Why an answer is what it is: answered, nothing relevant found, or the model said "not found". */
export type Reason = "ok" | "no_relevant_chunks" | "model_declined";

/** The reply of POST /chat. */
export interface ChatResponse {
  answer: string;
  found: boolean;
  reason: Reason;
  sources: Source[];
  conversation_id: string;
  /** The standalone question used for the search; null when the original was used. */
  rewritten_question: string | null;
}

/** One conversation in the list (GET /conversations), newest first. */
export interface ConversationSummary {
  id: string;
  title: string; // the first question, shortened
  created_at: string;
}

/**
 * One saved message. Assistant messages carry their sources and reason; the
 * backend does not store `found` or the rewritten question.
 */
export interface StoredMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  sources: Source[] | null;
  reason: string | null;
  created_at: string;
}

/** GET /conversations/{id}: the conversation with its messages, oldest first. */
export interface ConversationDetail extends ConversationSummary {
  messages: StoredMessage[];
}

/**
 * The one error type every API function throws.
 *
 * status is the HTTP status, or 0 when the backend could not be reached at all.
 * retryAfter (seconds) is set when the backend sent a Retry-After header (503).
 */
export class ApiError extends Error {
  readonly status: number;
  readonly retryAfter?: number;

  constructor(status: number, message: string, retryAfter?: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.retryAfter = retryAfter;
  }
}
