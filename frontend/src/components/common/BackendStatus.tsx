import { useCallback, useEffect, useRef, useState } from "react";

import { getHealth } from "../../api/documents";

/** How often /health is checked. It never calls the LLM, so this costs no quota. */
export const HEALTH_CHECK_MS = 30_000;

interface BackendStatusProps {
  /** Called when the backend answers again after being offline, so lists can reload. */
  onBackOnline?: () => void;
}

/**
 * A banner shown only while GET /health fails. Any failure counts as offline:
 * through the dev proxy a stopped backend gives an HTTP error, not a network error.
 *
 * It checks when the page opens, every 30 s, when the browser tab regains focus,
 * and when the user clicks "Check now".
 */
export function BackendStatus({ onBackOnline }: BackendStatusProps) {
  const [offline, setOffline] = useState(false);
  const [checking, setChecking] = useState(false);
  // Refs, read inside check(): the latest values without re-creating the function.
  const wasOffline = useRef(false);
  const onBackOnlineRef = useRef(onBackOnline);
  onBackOnlineRef.current = onBackOnline;

  const check = useCallback(async (): Promise<void> => {
    setChecking(true);
    try {
      await getHealth();
      if (wasOffline.current) {
        onBackOnlineRef.current?.();
      }
      wasOffline.current = false;
      setOffline(false);
    } catch {
      wasOffline.current = true;
      setOffline(true);
    } finally {
      setChecking(false);
    }
  }, []);

  useEffect(() => {
    void check();
    const timer = setInterval(() => void check(), HEALTH_CHECK_MS);
    // "focus" fires when the user comes back to this tab, e.g. after starting the backend.
    const onFocus = () => void check();
    window.addEventListener("focus", onFocus);
    return () => {
      clearInterval(timer);
      window.removeEventListener("focus", onFocus);
    };
  }, [check]);

  if (!offline) {
    return null;
  }
  return (
    <div
      role="alert"
      className="flex flex-wrap items-center gap-3 rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800"
    >
      <span className="flex-1">
        The StudyMate backend is not responding. Start it with{" "}
        <code>uvicorn app.main:app --reload</code> in the backend folder.
      </span>
      <button
        type="button"
        disabled={checking}
        onClick={() => void check()}
        className="rounded border border-red-700 px-3 py-1 disabled:opacity-50"
      >
        {checking ? "Checking…" : "Check now"}
      </button>
    </div>
  );
}
