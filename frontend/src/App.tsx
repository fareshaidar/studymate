import { useEffect, useState, type ChangeEvent } from "react";

import { getHealth, listDocuments } from "./api/documents";
import { ApiError, type DocumentInfo } from "./api/types";
import { uploadDocument, type UploadProgress } from "./api/upload";

type BackendState = "checking" | "online" | "offline";

/** Get a user-facing message from anything a promise rejected with. */
function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "Something went wrong.";
}

/**
 * Temporary smoke screen for step 1: proves the proxy, the error handling and
 * the upload progress work end to end. Replaced by the real layout in later steps.
 */
export default function App() {
  const [backend, setBackend] = useState<BackendState>("checking");
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [progress, setProgress] = useState<UploadProgress | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refresh(): Promise<void> {
    try {
      await getHealth();
      setBackend("online");
      setDocuments(await listDocuments());
    } catch (err) {
      setBackend("offline");
      setError(errorMessage(err));
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function handleFile(event: ChangeEvent<HTMLInputElement>): Promise<void> {
    const file = event.target.files?.[0];
    event.target.value = ""; // allow picking the same file again later
    if (!file) {
      return;
    }
    setError(null);
    try {
      await uploadDocument(file, setProgress);
      await refresh();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setProgress(null);
    }
  }

  return (
    <main className="mx-auto max-w-2xl space-y-6 p-6">
      <h1 className="text-2xl font-semibold">StudyMate (connection check)</h1>

      <p>
        Backend:{" "}
        <span className={backend === "online" ? "text-green-700" : "text-red-700"}>{backend}</span>
      </p>

      <label className="block">
        <span className="mb-1 block font-medium">Upload a PDF</span>
        <input
          type="file"
          accept="application/pdf"
          disabled={progress !== null}
          onChange={(event) => void handleFile(event)}
        />
      </label>

      {progress?.phase === "uploading" && (
        <p>
          Uploading… {Math.round((progress.loaded / progress.total) * 100)}%
        </p>
      )}
      {progress?.phase === "indexing" && <p>Indexing… (this can take a minute)</p>}
      {error && (
        <p role="alert" className="text-red-700">
          {error}
        </p>
      )}

      <section>
        <h2 className="mb-2 text-lg font-medium">Documents</h2>
        {documents.length === 0 ? (
          <p className="text-gray-600">No documents yet.</p>
        ) : (
          <ul className="list-disc pl-6">
            {documents.map((doc) => (
              <li key={doc.id}>
                {doc.filename} ({doc.page_count} pages)
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
