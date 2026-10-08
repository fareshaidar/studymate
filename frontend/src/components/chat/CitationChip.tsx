import type { Source } from "../../api/types";

interface CitationChipProps {
  source: Source;
  /** Whether this chip's card is currently open. */
  expanded: boolean;
  /** The id of the card element, so screen readers know what the button controls. */
  cardId: string;
  onClick: () => void;
}

/** A citation like [2] inside an answer, as a button that opens its source card. */
export function CitationChip({ source, expanded, cardId, onClick }: CitationChipProps) {
  return (
    <button
      type="button"
      aria-label={`Source ${source.n}: ${source.filename}, page ${source.page}`}
      aria-expanded={expanded}
      aria-controls={expanded ? cardId : undefined}
      onClick={onClick}
      className={`mx-0.5 rounded px-1 align-baseline text-xs font-medium ${
        expanded ? "bg-blue-700 text-white" : "bg-blue-100 text-blue-800 hover:bg-blue-200"
      }`}
    >
      [{source.n}]
    </button>
  );
}
