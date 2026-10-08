import { useRef, useState } from "react";

import { ApiError } from "../api/types";

/** A failed request. `id` is new for each failure, for use as ErrorNotice's key. */
export interface Failure {
  id: number;
  error: ApiError;
}

/**
 * State for one "press a button, wait, show the result" request, shared by the
 * three study panels: the latest result, whether it is running, and the last
 * failure, plus `retry` to run the last request again.
 *
 * `onFailure` is called once per failure, e.g. to reload the document list when
 * the backend says a selected document no longer exists.
 */
export function useRequest<T>(onFailure?: (error: ApiError) => void) {
  const [result, setResult] = useState<T | null>(null);
  const [pending, setPending] = useState(false);
  const [failure, setFailure] = useState<Failure | null>(null);
  // Refs: remembering these must not cause a re-render.
  const lastCall = useRef<(() => Promise<T>) | null>(null);
  const failureCount = useRef(0);

  async function run(call: () => Promise<T>): Promise<void> {
    lastCall.current = call;
    // Clear the old result: a new quiz must not show next to the previous one's answers.
    setResult(null);
    setFailure(null);
    setPending(true);
    try {
      setResult(await call());
    } catch (err) {
      const error = err instanceof ApiError ? err : new ApiError(0, "Something went wrong.");
      setFailure({ id: ++failureCount.current, error });
      onFailure?.(error);
    } finally {
      setPending(false);
    }
  }

  function retry(): void {
    if (lastCall.current) {
      void run(lastCall.current);
    }
  }

  return { result, pending, failure, run, retry };
}
