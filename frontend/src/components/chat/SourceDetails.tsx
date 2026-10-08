import { pdfPageUrl } from "../../api/documents";
import type { Source } from "../../api/types";

/** Filename, page, snippet and an "Open PDF at page n" link: shared by the citation card and the source list. */
export function SourceDetails({ source }: { source: Source }) {
  return (
    <div className="text-sm">
      <p>
        <span className="font-medium">{source.filename}</span>
        <span className="text-gray-600">, page {source.page}</span>
      </p>
      <p className="mt-1 text-gray-700 italic">“{source.snippet}”</p>
      <a
        href={pdfPageUrl(source.document_id, source.page)}
        // A new tab keeps the chat where it is; noopener stops the new page from controlling this one.
        target="_blank"
        rel="noopener noreferrer"
        className="mt-1 inline-block text-blue-700 underline"
      >
        Open PDF at page {source.page}
      </a>
    </div>
  );
}
