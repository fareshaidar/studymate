import { API_PREFIX } from "../proxy";
import { ApiError } from "./types";

export const OFFLINE_MESSAGE = "Cannot reach the StudyMate backend. Is it running?";

/** A user-facing message for anything a promise rejected with. */
export function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "Something went wrong.";
}

/** One item of FastAPI's 422 validation error list. */
interface ValidationItem {
  loc?: (string | number)[];
  msg?: string;
}

/** Turn FastAPI's 422 list into one readable sentence, e.g. "question: Field required". */
function describeValidationErrors(items: ValidationItem[]): string {
  const parts = items.map((item) => {
    const field = item.loc?.[item.loc.length - 1];
    const msg = item.msg ?? "invalid value";
    return field !== undefined ? `${field}: ${msg}` : msg;
  });
  return parts.length > 0 ? parts.join("; ") : "The request was not valid.";
}

/** Read a Retry-After header in seconds; the backend always sends a whole number. */
function parseRetryAfter(header: string | null): number | undefined {
  if (header === null) {
    return undefined;
  }
  const seconds = Number.parseInt(header, 10);
  return Number.isNaN(seconds) ? undefined : seconds;
}

/**
 * Build an ApiError from a failed response's status, raw body text and Retry-After header.
 *
 * It takes plain values (not a fetch Response) so the XHR upload can reuse it.
 * The backend usually sends {"detail": "<friendly text>"}, but FastAPI's own 422
 * errors send {"detail": [...]}, and a proxy error may send no JSON at all.
 */
export function buildApiError(
  status: number,
  bodyText: string,
  retryAfterHeader: string | null,
): ApiError {
  let message = `Request failed (HTTP ${status}).`;
  try {
    const body: unknown = JSON.parse(bodyText);
    if (typeof body === "object" && body !== null && "detail" in body) {
      const detail = (body as { detail: unknown }).detail;
      if (typeof detail === "string") {
        message = detail;
      } else if (Array.isArray(detail)) {
        message = describeValidationErrors(detail as ValidationItem[]);
      }
    }
  } catch {
    // Not JSON: keep the generic message.
  }
  return new ApiError(status, message, parseRetryAfter(retryAfterHeader));
}

/**
 * Call the backend with fetch and return the parsed JSON.
 *
 * Throws ApiError for every failure, so callers only handle one error type.
 * `path` is the backend route, e.g. "/documents"; the /api prefix is added here.
 */
export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(API_PREFIX + path, init);
  } catch {
    // fetch only rejects when no response arrived at all (server down, network error).
    throw new ApiError(0, OFFLINE_MESSAGE);
  }

  if (!response.ok) {
    const bodyText = await response.text();
    throw buildApiError(response.status, bodyText, response.headers.get("Retry-After"));
  }

  // 204 No Content (e.g. DELETE) has no body to parse.
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}
