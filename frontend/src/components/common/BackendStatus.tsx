import { useEffect, useState } from "react";

import { getHealth } from "../../api/documents";

/**
 * A banner shown only when GET /health fails. Any failure counts as offline:
 * through the dev proxy a stopped backend gives an HTTP error, not a network error.
 * Step 8 adds re-checking; for now it checks once when the page opens.
 */
export function BackendStatus() {
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    getHealth().then(
      () => setOffline(false),
      () => setOffline(true),
    );
  }, []);

  if (!offline) {
    return null;
  }
  return (
    <div role="alert" className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800">
      The StudyMate backend is not responding. Start it with{" "}
      <code>uvicorn app.main:app --reload</code> in the backend folder, then reload this page.
    </div>
  );
}
