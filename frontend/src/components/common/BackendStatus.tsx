import { useCallback, useEffect, useRef, useState } from "react";

import { getHealth } from "../../api/documents";

/** How often /health is checked. It never calls the LLM, so this costs no quota. */
export const HEALTH_CHECK_MS = 30_000;

interface BackendStatusProps {
  /** Called when the backend answers again after being offline, so lists can reload. */
  onBackOnline?: () => void;
}

/**
 * Banners from GET /health:
 * - offline (red) while it fails. Any failure counts: through the dev proxy a
 *   stopped backend gives an HTTP error, not a network error;
 * - no API key (amber) while the backend reports llm_configured: false. A backend
 *   that doesn't send the field (older version) counts as configured: no false alarm.
 *
 * It checks when the page opens, every 30 s, when the browser tab regains focus,
 * and when the user clicks "Check now".
 */
export function BackendStatus({ onBackOnline }: BackendStatusProps) {
  const [offline, setOffline] = useState(false);
  const [llmConfigured, setLlmConfigured] = useState(true);
  const [checking, setChecking] = useState(false);
  // Refs, read inside check(): the latest values without re-creating the function.
  const wasOffline = useRef(false);
  const onBackOnlineRef = useRef(onBackOnline);
  onBackOnlineRef.current = onBackOnline;

  const check = useCallback(async (): Promise<void> => {
    setChecking(true);
    try {
      const health = await getHealth();
      setLlmConfigured(health.llm_configured !== false);
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

  const checkNow = (
    <button
      type="button"
      disabled={checking}
      onClick={() => void check()}
      className="rounded border border-current px-3 py-1 disabled:opacity-50"
    >
      {checking ? "Checking…" : "Check now"}
    </button>
  );

  // Offline wins: without a backend, whether a key is set is unknown.
  if (offline) {
    return (
      <div
        role="alert"
        className="flex flex-wrap items-center gap-3 rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800"
      >
        <span className="flex-1">
          The StudyMate backend is not responding. Start it with{" "}
          <code>uvicorn app.main:app --reload</code> in the backend folder.
        </span>
        {checkNow}
      </div>
    );
  }
  if (!llmConfigured) {
    return (
      <div
        role="alert"
        className="flex flex-wrap items-center gap-3 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900"
      >
        <span className="flex-1">
          The AI isn't set up yet: add <code>GEMINI_API_KEY=&lt;your key&gt;</code> to{" "}
          <code>backend/.env</code>, then restart the backend. Uploading and browsing still work;
          questions and study tools need the key.
        </span>
        {checkNow}
      </div>
    );
  }
  return null;
}
