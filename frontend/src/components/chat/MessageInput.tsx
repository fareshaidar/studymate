import type { FormEvent, KeyboardEvent } from "react";

/** The backend rejects longer questions (ChatRequest.question max_length). */
export const MAX_QUESTION_CHARS = 2000;

interface MessageInputProps {
  /** The text in the box. The parent owns it, so it can put a failed question back. */
  value: string;
  onChange: (value: string) => void;
  /** Called with the trimmed question; never with an empty one. */
  onSend: (question: string) => void;
  disabled: boolean;
}

/** The question box: Enter sends, Shift+Enter starts a new line. */
export function MessageInput({ value, onChange, onSend, disabled }: MessageInputProps) {
  function submit(): void {
    const question = value.trim();
    if (question && !disabled) {
      onSend(question);
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault(); // stay on the page instead of a browser form submit
    submit();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>): void {
    // isComposing: Enter that confirms an IME input (e.g. Japanese) must not send.
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex items-end gap-2">
      <textarea
        aria-label="Your question"
        placeholder="Ask a question about your documents…"
        rows={2}
        maxLength={MAX_QUESTION_CHARS}
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={handleKeyDown}
        className="flex-1 resize-none rounded-lg border border-gray-300 p-2 disabled:bg-gray-100"
      />
      <button
        type="submit"
        disabled={disabled || value.trim() === ""}
        className="rounded-lg bg-blue-700 px-4 py-2 text-white disabled:opacity-50"
      >
        Send
      </button>
    </form>
  );
}
