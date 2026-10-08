import { useEffect, useState } from "react";

import { DOCUMENT_NOT_FOUND, type ApiError } from "../../api/types";

interface ErrorNoticeProps {
  error: ApiError;
  /** Shown as a Retry button when retrying can help. */
  onRetry?: () => void;
  /** Shown as "Start a new chat" on a 404 for a conversation that no longer exists. */
  onNewChat?: () => void;
}

/**
 * A failed request: the backend's friendly message plus what the user can do.
 *
 * On a 503 with Retry-After, Retry stays disabled while a countdown runs, so the
 * user doesn't hit the rate limit again. Give this component a new `key` for
 * each new error, so the countdown starts fresh.
 */
export function ErrorNotice({ error, onRetry, onNewChat }: ErrorNoticeProps) {
  const [secondsLeft, setSecondsLeft] = useState(
    error.status === 503 ? (error.retryAfter ?? 0) : 0,
  );

  // Tick once a second until the countdown reaches 0.
  useEffect(() => {
    if (secondsLeft <= 0) {
      return;
    }
    const timer = setTimeout(() => setSecondsLeft((s) => s - 1), 1000);
    return () => clearTimeout(timer);
  }, [secondsLeft]);

  // A deleted document: the chat or study panel has already asked App to reload the
  // document list, which drops the stale ticks, so sending again is all it takes.
  const documentsGone = error.code === DOCUMENT_NOT_FOUND;
  // "Start a new chat" fixes a missing conversation, but not a missing document.
  const offerNewChat = error.status === 404 && !documentsGone;
  // No Retry where retrying fails the same way: 404, 422 (invalid request) and 429
  // (the AI service's daily limit is used up until tomorrow).
  const noRetryStatuses = [404, 422, 429];
  const canRetry = onRetry !== undefined && !noRetryStatuses.includes(error.status);

  return (
    <div role="alert" className="rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-900">
      <p>{error.message}</p>
      {documentsGone && (
        <p className="mt-1">The document list has been refreshed; please try again.</p>
      )}
      {secondsLeft > 0 && <p className="mt-1">Busy: try again in {secondsLeft} s.</p>}
      <div className="mt-2 flex gap-2">
        {canRetry && (
          <button
            type="button"
            className="rounded bg-red-700 px-3 py-1 text-white disabled:opacity-50"
            disabled={secondsLeft > 0}
            onClick={onRetry}
          >
            Retry
          </button>
        )}
        {offerNewChat && onNewChat && (
          <button type="button" className="rounded border border-red-700 px-3 py-1" onClick={onNewChat}>
            Start a new chat
          </button>
        )}
      </div>
    </div>
  );
}
