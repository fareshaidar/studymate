import { useState } from "react";

import { getFlashcards, MAX_FLASHCARDS } from "../../api/study";
import type { Flashcard, FlashcardsResponse } from "../../api/types";
import { useRequest } from "../../lib/useRequest";
import { ErrorNotice } from "../common/ErrorNotice";
import { NotFoundNotice } from "../common/NotFoundNotice";
import { ItemSourceLink } from "./ItemSourceLink";
import { reloadIfDocumentsMissing, StudyForm, type StudyPanelProps } from "./StudyForm";

/** Flashcards from the ticked documents, shown one at a time. */
export function FlashcardsPanel({ documentIds, disabled = false, onDocumentsMissing }: StudyPanelProps) {
  const { result, pending, failure, run, retry } = useRequest<FlashcardsResponse>(
    reloadIfDocumentsMissing(onDocumentsMissing),
  );

  return (
    <div className="space-y-4">
      <StudyForm
        buttonLabel="Make flashcards"
        pending={pending}
        disabled={disabled}
        count={{ label: "Cards", initial: 10, max: MAX_FLASHCARDS }}
        onGenerate={(topic, numCards) => void run(() => getFlashcards({ documentIds, topic, numCards }))}
      />
      {pending && (
        <p role="status" className="text-sm text-gray-500">
          Writing flashcards…
        </p>
      )}
      {failure && <ErrorNotice key={failure.id} error={failure.error} onRetry={retry} />}
      {result && !result.found && <NotFoundNotice message={result.message ?? undefined} />}
      {result?.found && result.cards.length > 0 && <Deck cards={result.cards} />}
    </div>
  );
}

/** One card at a time: click to flip, Previous/Next to move. */
function Deck({ cards }: { cards: Flashcard[] }) {
  const [index, setIndex] = useState(0);
  const [flipped, setFlipped] = useState(false);
  const card = cards[index];

  function goTo(newIndex: number): void {
    setIndex(newIndex);
    setFlipped(false); // every card starts on its question side
  }

  return (
    <div className="max-w-xl space-y-3">
      <p className="text-sm text-gray-600">
        Card {index + 1} of {cards.length} · click the card to flip it
      </p>
      <button
        type="button"
        aria-pressed={flipped}
        onClick={() => setFlipped(!flipped)}
        className={`block min-h-40 w-full rounded-lg border p-6 text-left shadow-sm ${
          flipped ? "border-green-300 bg-green-50" : "border-gray-200 bg-white"
        }`}
      >
        <span className="block text-xs font-semibold text-gray-500 uppercase">
          {flipped ? "Answer" : "Question"}
        </span>
        <span className="mt-2 block text-lg whitespace-pre-wrap">{flipped ? card.back : card.front}</span>
      </button>
      {/* Outside the card: a link inside a button is not allowed in HTML. */}
      {flipped && <ItemSourceLink source={card.source} />}
      <div className="flex gap-2">
        <button
          type="button"
          disabled={index === 0}
          onClick={() => goTo(index - 1)}
          className="rounded border px-3 py-1 disabled:opacity-50"
        >
          Previous
        </button>
        <button
          type="button"
          disabled={index === cards.length - 1}
          onClick={() => goTo(index + 1)}
          className="rounded border px-3 py-1 disabled:opacity-50"
        >
          Next
        </button>
      </div>
    </div>
  );
}
