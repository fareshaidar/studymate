import { pdfPageUrl } from "../../api/documents";
import type { ItemSource } from "../../api/types";

/** "Source: biology.pdf, page 4 · Open PDF at page 4" under a quiz answer or flashcard. */
export function ItemSourceLink({ source }: { source: ItemSource }) {
  return (
    <p className="text-sm text-gray-700">
      Source: {source.filename}, page {source.page} ·{" "}
      <a
        href={pdfPageUrl(source.document_id, source.page)}
        target="_blank"
        rel="noopener noreferrer"
        className="text-blue-700 underline"
      >
        Open PDF at page {source.page}
      </a>
    </p>
  );
}
