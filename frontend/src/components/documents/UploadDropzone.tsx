import { useState, type ChangeEvent, type DragEvent } from "react";

import { errorMessage } from "../../api/client";
import { uploadDocument, type UploadProgress } from "../../api/upload";

interface UploadDropzoneProps {
  /** Called after a successful upload, so the document list can refresh. */
  onUploaded: () => void | Promise<void>;
}

/**
 * Upload one PDF at a time, by drag and drop or the file picker.
 *
 * Shows the bytes sent, then an indexing message while the backend embeds the
 * PDF (the request only finishes after indexing). Errors stay inline.
 */
export function UploadDropzone({ onUploaded }: UploadDropzoneProps) {
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState<UploadProgress | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  async function startUpload(file: File): Promise<void> {
    setError(null);
    // A dropped file skips the picker's accept filter, so check here too. The
    // backend still validates; this just gives a faster, friendlier message.
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setError("Only PDF files are supported.");
      return;
    }
    setBusy(true);
    try {
      await uploadDocument(file, setProgress);
      await onUploaded();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
      setProgress(null);
    }
  }

  function handlePick(event: ChangeEvent<HTMLInputElement>): void {
    const file = event.target.files?.[0];
    event.target.value = ""; // so picking the same file again still fires onChange
    if (file) {
      void startUpload(file);
    }
  }

  function handleDragOver(event: DragEvent<HTMLDivElement>): void {
    event.preventDefault(); // required, or the browser refuses the drop
    if (!busy) {
      setDragging(true);
    }
  }

  function handleDrop(event: DragEvent<HTMLDivElement>): void {
    event.preventDefault(); // stop the browser from opening the file itself
    setDragging(false);
    const file = event.dataTransfer.files[0];
    if (!busy && file) {
      void startUpload(file);
    }
  }

  const border = dragging ? "border-blue-500 bg-blue-50" : "border-gray-300";

  return (
    <div
      onDragOver={handleDragOver}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      className={`rounded-lg border-2 border-dashed p-4 text-sm ${border}`}
    >
      <label className={busy ? "cursor-not-allowed text-gray-400" : "cursor-pointer"}>
        <input
          type="file"
          accept=".pdf,application/pdf"
          aria-label="Choose a PDF file"
          className="sr-only"
          disabled={busy}
          onChange={handlePick}
        />
        Drop a PDF here or <span className="text-blue-700 underline">choose a file</span>
      </label>

      {busy && progress === null && <p className="mt-2">Starting upload…</p>}
      {progress?.phase === "uploading" && (
        <div className="mt-2">
          <progress
            className="w-full"
            value={progress.loaded}
            max={progress.total}
            aria-label="Upload progress"
          />
          <p>Uploading… {Math.round((progress.loaded / progress.total) * 100)}%</p>
        </div>
      )}
      {progress?.phase === "indexing" && (
        <p role="status" className="mt-2">
          Indexing… this can take a minute for long PDFs.
        </p>
      )}
      {error && (
        <p role="alert" className="mt-2 text-red-700">
          {error}
        </p>
      )}
    </div>
  );
}
