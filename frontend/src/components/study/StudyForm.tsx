import { useId, useState, type FormEvent } from "react";

import { MAX_TOPIC_CHARS } from "../../api/study";

/** Props shared by the three study panels. */
export interface StudyPanelProps {
  /** Ticked documents; empty means "use all documents". */
  documentIds: string[];
  /** True when there is nothing to study yet (no PDF uploaded). */
  disabled?: boolean;
}

interface StudyFormProps {
  /** The Generate button's text, e.g. "Make quiz". */
  buttonLabel: string;
  pending: boolean;
  /** Called with the topic (may be blank) and the count (already within limits). */
  onGenerate: (topic: string, count: number) => void;
  /** The "how many" field; left out for the summary, which has no count. */
  count?: { label: string; initial: number; max: number };
  /** Blocks generating, e.g. when no PDF is uploaded yet. */
  disabled?: boolean;
}

/** The settings shared by the study tools: an optional topic and, for quiz and flashcards, a count. */
export function StudyForm({ buttonLabel, pending, onGenerate, count, disabled = false }: StudyFormProps) {
  const [topic, setTopic] = useState("");
  // Kept as text so the field can be empty while the user types a new number.
  const [countText, setCountText] = useState(String(count?.initial ?? 1));
  const topicId = useId();
  const countId = useId();

  function handleSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    let value = count?.initial ?? 1;
    if (count) {
      const typed = Number.parseInt(countText, 10);
      // The input's min/max make the browser block out-of-range numbers with its
      // own message. An empty field is still valid, so it falls back to the
      // default; the clamp is only a safety net.
      value = Number.isNaN(typed) ? count.initial : Math.min(Math.max(typed, 1), count.max);
      setCountText(String(value));
    }
    onGenerate(topic, value);
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-wrap items-end gap-3">
      <div className="min-w-48 flex-1">
        <label htmlFor={topicId} className="block text-sm font-medium">
          Topic (optional)
        </label>
        <input
          id={topicId}
          type="text"
          value={topic}
          maxLength={MAX_TOPIC_CHARS}
          placeholder="e.g. photosynthesis"
          onChange={(event) => setTopic(event.target.value)}
          className="w-full rounded border border-gray-300 p-2"
        />
      </div>
      {count && (
        <div>
          <label htmlFor={countId} className="block text-sm font-medium">
            {count.label}
          </label>
          <input
            id={countId}
            type="number"
            min={1}
            max={count.max}
            value={countText}
            onChange={(event) => setCountText(event.target.value)}
            className="w-20 rounded border border-gray-300 p-2"
          />
        </div>
      )}
      <button
        type="submit"
        disabled={pending || disabled}
        className="rounded-lg bg-blue-700 px-4 py-2 text-white disabled:opacity-50"
      >
        {buttonLabel}
      </button>
    </form>
  );
}
