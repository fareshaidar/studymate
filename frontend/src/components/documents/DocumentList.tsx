import type { DocumentInfo } from "../../api/types";
import { DeleteWithConfirm } from "../common/DeleteWithConfirm";

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

/** One document: a search-scope checkbox, its name and pages, and a two-click delete. */
function DocumentRow({ doc, checked, onToggle, onDelete }: DocumentRowProps) {
  return (
    <li className="rounded p-2 text-sm hover:bg-gray-100">
      <DeleteWithConfirm name={doc.filename} onDelete={onDelete}>
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
        </div>
      </DeleteWithConfirm>
    </li>
  );
}
