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
