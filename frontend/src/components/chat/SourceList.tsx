import type { Source } from "../../api/types";
import { SourceDetails } from "./SourceDetails";

interface SourceListProps {
  sources: Source[];
  /** Ids of documents that still exist; see SourceDetails. */
  existingDocumentIds?: Set<string>;
}

/**
 * The passages behind an answer. Cited ones are shown; the others the search
 * also found are folded away, since they were given to the model but not used.
 */
export function SourceList({ sources, existingDocumentIds }: SourceListProps) {
  if (sources.length === 0) {
    return null;
  }
  const sorted = [...sources].sort((a, b) => a.n - b.n);
  const cited = sorted.filter((source) => source.cited);
  const others = sorted.filter((source) => !source.cited);

  return (
    <div className="mt-3 space-y-2 border-t border-gray-200 pt-2">
      {cited.length > 0 && (
        <>
          <h3 className="text-xs font-semibold text-gray-600 uppercase">Sources</h3>
          <ul className="space-y-2">
            {cited.map((source) => (
              <SourceItem key={source.n} source={source} existingDocumentIds={existingDocumentIds} />
            ))}
          </ul>
        </>
      )}
      {others.length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer text-gray-600">
            Other retrieved passages ({others.length})
          </summary>
          <ul className="mt-2 space-y-2">
            {others.map((source) => (
              <SourceItem key={source.n} source={source} existingDocumentIds={existingDocumentIds} />
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

function SourceItem({ source, existingDocumentIds }: { source: Source; existingDocumentIds?: Set<string> }) {
  return (
    <li className="flex gap-2">
      <span className="text-xs font-medium text-blue-800">[{source.n}]</span>
      <SourceDetails source={source} existingDocumentIds={existingDocumentIds} />
    </li>
  );
}
