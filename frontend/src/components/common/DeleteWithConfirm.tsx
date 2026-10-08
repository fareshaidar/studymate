import { useEffect, useRef, useState, type ReactNode } from "react";

import { errorMessage } from "../../api/client";

interface DeleteWithConfirmProps {
  /** What is being deleted, e.g. "biology.pdf"; used in the button name and the question. */
  name: string;
  /** Deletes the item; a rejection is shown under the row. */
  onDelete: () => Promise<void>;
  /** The row's own content, shown to the left of the Delete button. */
  children: ReactNode;
}

/**
 * A list row with a two-click delete: the Delete button, then an inline
 * "Delete <name>?" confirm. Used for documents and conversations.
 *
 * Inline instead of window.confirm: it can be styled, reached by keyboard
 * like the rest of the page, and tested.
 */
export function DeleteWithConfirm({ name, onDelete, children }: DeleteWithConfirmProps) {
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const deleteButton = useRef<HTMLButtonElement>(null);
  const confirmButton = useRef<HTMLButtonElement>(null);
  const wasConfirming = useRef(false);

  // Keyboard users: the Delete button disappears when the confirm opens, so
  // focus moves to the confirm button, and back to Delete when it closes.
  useEffect(() => {
    if (confirming) {
      confirmButton.current?.focus();
    } else if (wasConfirming.current) {
      deleteButton.current?.focus();
    }
    wasConfirming.current = confirming;
  }, [confirming]);

  async function confirmDelete(): Promise<void> {
    setDeleting(true);
    setError(null);
    try {
      await onDelete();
      // On success the parent refreshes its list and this row disappears.
    } catch (err) {
      setError(errorMessage(err));
      setDeleting(false);
      setConfirming(false);
    }
  }

  return (
    <div>
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">{children}</div>
        {!confirming && (
          <button
            ref={deleteButton}
            type="button"
            aria-label={`Delete ${name}`}
            className="text-gray-500 hover:text-red-700"
            onClick={() => setConfirming(true)}
          >
            Delete
          </button>
        )}
      </div>

      {confirming && (
        <div className="mt-2 flex items-center gap-2">
          <span className="min-w-0 flex-1 truncate">Delete {name}?</span>
          <button
            ref={confirmButton}
            type="button"
            className="rounded bg-red-700 px-2 py-1 text-white disabled:opacity-50"
            disabled={deleting}
            onClick={() => void confirmDelete()}
          >
            {deleting ? "Deleting…" : "Delete"}
          </button>
          <button
            type="button"
            className="rounded border px-2 py-1"
            disabled={deleting}
            onClick={() => setConfirming(false)}
          >
            Cancel
          </button>
        </div>
      )}
      {error && (
        <p role="alert" className="mt-1 text-red-700">
          {error}
        </p>
      )}
    </div>
  );
}
