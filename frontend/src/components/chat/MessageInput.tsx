import type { FormEvent, KeyboardEvent, RefObject } from "react";

/** The backend rejects longer questions (ChatRequest.question max_length). */
export const MAX_QUESTION_CHARS = 2000;

interface MessageInputProps {
  /** The text in the box. The parent owns it, so it can put a failed question back. */
  value: string;
  onChange: (value: string) => void;
  /** Called with the trimmed question; never with an empty one. */
  onSend: (question: string) => void;
  /**
   * True while an answer is loading. The box stays editable (a disabled
   * element loses keyboard focus, and you may want to type the next question),
   * but nothing can be sent until the answer arrives.
   */
  sending: boolean;
  /** Fully disabled, e.g. when there are no documents to ask about. */
  disabled?: boolean;
  /** Lets the parent put focus back in the box. */
  inputRef?: RefObject<HTMLTextAreaElement | null>;
}

/** The question box: Enter sends, Shift+Enter starts a new line. */
export function MessageInput({
  value,
  onChange,
  onSend,
  sending,
  disabled = false,
  inputRef,
}: MessageInputProps) {
  function submit(): void {
    const question = value.trim();
    if (question && !sending && !disabled) {
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
        ref={inputRef}
        aria-label="Your question"
        placeholder="Ask a question about your documents…"
        rows={2}
        maxLength={MAX_QUESTION_CHARS}
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={handleKeyDown}
        className="min-w-0 flex-1 resize-none rounded-lg border border-gray-300 p-2 disabled:bg-gray-100"
      />
      <button
        type="submit"
        disabled={disabled || sending || value.trim() === ""}
        className="rounded-lg bg-blue-700 px-4 py-2 text-white disabled:opacity-50"
      >
        Send
      </button>
    </form>
  );
}
