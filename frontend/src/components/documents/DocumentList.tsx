import { useState } from "react";

import { errorMessage } from "../../api/client";
import type { DocumentInfo } from "../../api/types";

interface DocumentListProps {
  documents: DocumentInfo[];
  /** Ticked document ids; empty means "search all documents". */
  selectedIds: string[];
  onSelectionChange: (ids: string[]) => void;
  /** Deletes the document; a rejection is shown on that document's row. */
  onDelete: (id: string) => Promise<void>;
}

/** The uploaded PDFs, each with a search-scope checkbox and a delete button. */
export function DocumentList({
  documents,
  selectedIds,
  onSelectionChange,
  onDelete,
}: DocumentListProps) {
  if (documents.length === 0) {
    return <p className="text-sm text-gray-600">No documents yet. Upload a PDF to get started.</p>;
  }

  function toggle(id: string, checked: boolean): void {
    onSelectionChange(checked ? [...selectedIds, id] : selectedIds.filter((x) => x !== id));
  }

  const total = documents.length;
  const scope =
    selectedIds.length === 0
      ? "Searching all documents"
      : `Searching ${selectedIds.length} of ${total} document${total === 1 ? "" : "s"}`;

  return (
    <div className="space-y-2">
      <p className="text-xs text-gray-600">{scope}</p>
      <ul className="space-y-1">
        {documents.map((doc) => (
          <DocumentRow
            key={doc.id}
            doc={doc}
            checked={selectedIds.includes(doc.id)}
            onToggle={(checked) => toggle(doc.id, checked)}
            onDelete={() => onDelete(doc.id)}
          />
        ))}
      </ul>
    </div>
  );
}

interface DocumentRowProps {
  doc: DocumentInfo;
  checked: boolean;
  onToggle: (checked: boolean) => void;
  onDelete: () => Promise<void>;
}

/** One document. Delete is two clicks: the button, then an inline confirm. */
function DocumentRow({ doc, checked, onToggle, onDelete }: DocumentRowProps) {
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function confirmDelete(): Promise<void> {
    setDeleting(true);
    setError(null);
    try {
      await onDelete();
      // On success the parent refreshes the list and this row disappears.
    } catch (err) {
      setError(errorMessage(err));
      setDeleting(false);
      setConfirming(false);
    }
  }

  return (
    <li className="rounded p-2 text-sm hover:bg-gray-100">
      <div className="flex items-start gap-2">
        <input
          id={`doc-${doc.id}`}
          type="checkbox"
          className="mt-1"
          checked={checked}
          onChange={(event) => onToggle(event.target.checked)}
        />
        <label htmlFor={`doc-${doc.id}`} className="min-w-0 flex-1">
          <span className="block truncate" title={doc.filename}>
            {doc.filename}
          </span>
          <span className="text-xs text-gray-600">
            {doc.page_count} page{doc.page_count === 1 ? "" : "s"}
          </span>
        </label>
        {!confirming && (
          <button
            type="button"
            aria-label={`Delete ${doc.filename}`}
            className="text-gray-500 hover:text-red-700"
            onClick={() => setConfirming(true)}
          >
            Delete
          </button>
        )}
      </div>

      {confirming && (
        <div className="mt-2 flex items-center gap-2">
          <span className="flex-1">Delete {doc.filename}?</span>
          <button
            type="button"
            className="rounded bg-red-700 px-2 py-1 text-white disabled:opacity-50"
            disabled={deleting}
            onClick={() => void confirmDelete()}
          >
            {deleting ? "Deleting…" : "Delete"}
          </button>
          <button
            type="button"
            className="rounded border px-2 py-1"
            disabled={deleting}
            onClick={() => setConfirming(false)}
          >
            Cancel
          </button>
        </div>
      )}
      {error && (
        <p role="alert" className="mt-1 text-red-700">
          {error}
        </p>
      )}
    </li>
  );
}
