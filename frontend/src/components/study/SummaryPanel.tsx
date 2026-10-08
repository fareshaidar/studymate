import { pdfPageUrl } from "../../api/documents";
import { getSummary } from "../../api/study";
import type { SummaryResponse } from "../../api/types";
import { formatPageRanges } from "../../lib/pages";
import { useRequest } from "../../lib/useRequest";
import { ErrorNotice } from "../common/ErrorNotice";
import { NotFoundNotice } from "../common/NotFoundNotice";
import { StudyForm, type StudyPanelProps } from "./StudyForm";

/** A summary of the ticked documents, optionally focused on one topic. */
export function SummaryPanel({ documentIds, disabled = false }: StudyPanelProps) {
  const { result, pending, failure, run, retry } = useRequest<SummaryResponse>();

  return (
    <div className="space-y-4">
      <StudyForm
        buttonLabel="Summarise"
        pending={pending}
        disabled={disabled}
        onGenerate={(topic) => void run(() => getSummary({ documentIds, topic }))}
      />
      {pending && (
        <p role="status" className="text-sm text-gray-500">
          Summarising… long documents can take a minute.
        </p>
      )}
      {failure && <ErrorNotice key={failure.id} error={failure.error} onRetry={retry} />}
      {result && !result.found && <NotFoundNotice message={result.message ?? undefined} />}
      {result?.found && <SummaryResult summary={result} />}
    </div>
  );
}

function SummaryResult({ summary }: { summary: SummaryResponse }) {
  return (
    <article className="space-y-3 rounded-lg bg-white p-4 shadow-sm">
      {summary.truncated && (
        <p className="rounded border border-amber-300 bg-amber-50 p-2 text-sm">
          Partial summary: part of the material was skipped to stay within the AI call limit. Pick
          fewer documents or a topic for a complete one.
        </p>
      )}
      {/* pre-wrap keeps the model's paragraphs and "- " bullets */}
      <p className="whitespace-pre-wrap">{summary.summary}</p>
      {summary.pages.length > 0 && (
        <div className="border-t border-gray-200 pt-2 text-sm">
          <h3 className="text-xs font-semibold text-gray-600 uppercase">Based on</h3>
          <ul className="mt-1 space-y-1">
            {summary.pages.map((doc) => (
              <li key={doc.document_id}>
                {doc.filename}, page{doc.pages.length === 1 ? "" : "s"} {formatPageRanges(doc.pages)}
                {doc.pages.length > 0 && (
                  <>
                    {" · "}
                    <a
                      href={pdfPageUrl(doc.document_id, Math.min(...doc.pages))}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-blue-700 underline"
                    >
                      Open PDF
                    </a>
                  </>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </article>
  );
}
