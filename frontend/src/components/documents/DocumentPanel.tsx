import { deleteDocument } from "../../api/documents";
import type { DocumentInfo } from "../../api/types";
import { DocumentList } from "./DocumentList";
import { UploadDropzone } from "./UploadDropzone";

interface DocumentPanelProps {
  /** null while the list is still loading. */
  documents: DocumentInfo[] | null;
  listError: string | null;
  selectedIds: string[];
  onSelectionChange: (ids: string[]) => void;
  /** Reloads the list after an upload or a delete. */
  onDocumentsChanged: () => Promise<void>;
}

/** The sidebar section for uploading, choosing and deleting documents. */
export function DocumentPanel({
  documents,
  listError,
  selectedIds,
  onSelectionChange,
  onDocumentsChanged,
}: DocumentPanelProps) {
  async function handleDelete(id: string): Promise<void> {
    await deleteDocument(id); // errors propagate to the row, which shows them
    await onDocumentsChanged();
  }

  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold">Documents</h2>
      <UploadDropzone onUploaded={onDocumentsChanged} />
      {listError && (
        <p role="alert" className="text-sm text-red-700">
          Could not load documents: {listError}
        </p>
      )}
      {documents === null && !listError && <p className="text-sm text-gray-600">Loading documents…</p>}
      {documents !== null && (
        <DocumentList
          documents={documents}
          selectedIds={selectedIds}
          onSelectionChange={onSelectionChange}
          onDelete={handleDelete}
        />
      )}
    </section>
  );
}
