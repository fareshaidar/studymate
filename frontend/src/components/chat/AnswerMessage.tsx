import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";

import type { Source } from "../../api/types";
import { parseAnswer } from "../../lib/citations";
import { NotFoundNotice } from "../common/NotFoundNotice";
import { CitationChip } from "./CitationChip";
import { SourceDetails } from "./SourceDetails";
import { SourceList } from "./SourceList";

interface AnswerMessageProps {
  answer: string;
  found: boolean;
  /** Why the answer is what it is; stored messages may have null. */
  reason: string | null;
  sources: Source[];
  /** Ids of documents that still exist; see SourceDetails. */
  existingDocumentIds?: Set<string>;
}

/**
 * One assistant answer: the text with clickable [n] chips, a card for the
 * chip that is open, and the list of sources underneath.
 */
export function AnswerMessage({
  answer,
  found,
  reason,
  sources,
  existingDocumentIds,
}: AnswerMessageProps) {
  const [openN, setOpenN] = useState<number | null>(null);
  // Unique per message, so several answers on one page never share an id.
  const cardId = useId();
  const cardRef = useRef<HTMLDivElement>(null);
  // The chip that opened the card: the same [n] can appear more than once,
  // so focus must go back to the one the user actually pressed.
  const opener = useRef<HTMLButtonElement | null>(null);

  // Move keyboard and screen-reader focus into the card when it opens.
  useEffect(() => {
    if (openN !== null) {
      cardRef.current?.focus();
    }
  }, [openN]);

  if (!found) {
    return <NotFoundNotice reason={reason} />;
  }

  const segments = parseAnswer(answer, sources);
  const openSource = sources.find((source) => source.n === openN);

  function closeCard(): void {
    setOpenN(null);
    opener.current?.focus();
  }

  function toggleCard(n: number, chip: HTMLButtonElement): void {
    if (openN === n) {
      closeCard(); // clicking the open chip again closes its card
      return;
    }
    opener.current = chip;
    setOpenN(n);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>): void {
    if (event.key === "Escape" && openN !== null) {
      closeCard();
    }
  }

  return (
    <div onKeyDown={handleKeyDown} className="rounded-lg bg-white p-3 shadow-sm">
      {/* pre-wrap keeps the model's line breaks and "- " bullets without a Markdown library */}
      <p className="whitespace-pre-wrap">
        {segments.map((segment, index) =>
          segment.kind === "text" ? (
            <span key={index}>{segment.text}</span>
          ) : (
            <CitationChip
              key={index}
              source={segment.source}
              expanded={openN === segment.source.n}
              cardId={cardId}
              onClick={(chip) => toggleCard(segment.source.n, chip)}
            />
          ),
        )}
      </p>

      {openSource && (
        <div
          ref={cardRef}
          id={cardId}
          role="region"
          aria-label={`Source ${openSource.n}`}
          // -1: focusable by code (above) but not an extra stop in the Tab order.
          tabIndex={-1}
          className="mt-2 rounded border border-blue-200 bg-blue-50 p-2"
        >
          <div className="flex items-start justify-between gap-2">
            <SourceDetails source={openSource} existingDocumentIds={existingDocumentIds} />
            <button
              type="button"
              aria-label="Close source"
              className="text-gray-500 hover:text-gray-900"
              onClick={closeCard}
            >
              ×
            </button>
          </div>
        </div>
      )}

      <SourceList sources={sources} existingDocumentIds={existingDocumentIds} />
    </div>
  );
}
