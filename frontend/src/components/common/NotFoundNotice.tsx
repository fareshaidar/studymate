interface NotFoundNoticeProps {
  /** The chat's `reason`; unknown or missing values get a generic line. */
  reason?: string | null;
  /** A message from the backend (the study tools send one); wins over `reason`. */
  message?: string;
}

/** Plain-words versions of the chat's "not found" reasons. */
const REASON_TEXT: Record<string, string> = {
  no_relevant_chunks: "No passage in the selected documents was close enough to your question.",
  model_declined: "Some passages looked related, but none of them contained the answer.",
};

/**
 * Shown instead of an answer when the material doesn't contain it. Saying so
 * plainly (rather than guessing) is the point of the app, so this is not styled as an error.
 */
export function NotFoundNotice({ reason, message }: NotFoundNoticeProps) {
  const explanation =
    message ?? (reason ? REASON_TEXT[reason] : undefined) ?? "Your documents don't seem to cover this.";

  return (
    <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm">
      <p className="font-semibold">Not found in your material</p>
      <p className="mt-1">{explanation}</p>
      <p className="mt-1 text-gray-700">
        Try rephrasing with words from your notes, or select more documents (or none, to search all
        of them).
      </p>
    </div>
  );
}
