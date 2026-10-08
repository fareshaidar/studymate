import { useState } from "react";

import { FlashcardsPanel } from "./FlashcardsPanel";
import { QuizPanel } from "./QuizPanel";
import { SummaryPanel } from "./SummaryPanel";

type Tool = "summary" | "quiz" | "flashcards";

const TOOLS: { id: Tool; label: string }[] = [
  { id: "summary", label: "Summary" },
  { id: "quiz", label: "Quiz" },
  { id: "flashcards", label: "Flashcards" },
];

interface StudyViewProps {
  /** The current chat's ticked documents; empty means "use all documents". */
  documentIds: string[];
  /** How many documents exist, for the scope line. */
  documentCount: number;
}

/** The study tools. All three panels stay mounted, so a result survives switching tools. */
export function StudyView({ documentIds, documentCount }: StudyViewProps) {
  const [tool, setTool] = useState<Tool>("summary");

  const scope =
    documentIds.length === 0
      ? "Using all documents"
      : `Using ${documentIds.length} of ${documentCount} document${documentCount === 1 ? "" : "s"}`;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        {TOOLS.map(({ id, label }) => (
          <button
            key={id}
            type="button"
            aria-pressed={tool === id}
            onClick={() => setTool(id)}
            className={`rounded-full px-3 py-1 text-sm ${
              tool === id ? "bg-blue-700 text-white" : "bg-gray-200 hover:bg-gray-300"
            }`}
          >
            {label}
          </button>
        ))}
        <span className="text-xs text-gray-600">{scope} (change it with the ticks in the sidebar)</span>
      </div>
      <div hidden={tool !== "summary"}>
        <SummaryPanel documentIds={documentIds} />
      </div>
      <div hidden={tool !== "quiz"}>
        <QuizPanel documentIds={documentIds} />
      </div>
      <div hidden={tool !== "flashcards"}>
        <FlashcardsPanel documentIds={documentIds} />
      </div>
    </div>
  );
}
