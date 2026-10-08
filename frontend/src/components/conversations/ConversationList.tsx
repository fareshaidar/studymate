import type { ConversationSummary } from "../../api/types";
import { DeleteWithConfirm } from "../common/DeleteWithConfirm";

interface ConversationListProps {
  /** null while the list is still loading. */
  conversations: ConversationSummary[] | null;
  listError: string | null;
  /** The conversation on screen, or null for a new chat. */
  activeId: string | null;
  onOpen: (id: string) => void;
  onNewChat: () => void;
  /** Deletes a conversation; a rejection is shown on its row. */
  onDelete: (id: string) => Promise<void>;
}

/** Short local date, e.g. "8 Oct 2026", for a conversation's creation time. */
function formatDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return date.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

/** The sidebar list of past chats, with "New chat", open and delete. */
export function ConversationList({
  conversations,
  listError,
  activeId,
  onOpen,
  onNewChat,
  onDelete,
}: ConversationListProps) {
  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Conversations</h2>
        <button
          type="button"
          onClick={onNewChat}
          className="rounded border border-blue-700 px-2 py-1 text-sm text-blue-700 hover:bg-blue-50"
        >
          New chat
        </button>
      </div>

      {listError && (
        <p role="alert" className="text-sm text-red-700">
          Could not load conversations: {listError}
        </p>
      )}
      {conversations === null && !listError && (
        <p className="text-sm text-gray-600">Loading conversations…</p>
      )}
      {conversations?.length === 0 && (
        <p className="text-sm text-gray-600">No conversations yet. Ask a question to start one.</p>
      )}
      {conversations && conversations.length > 0 && (
        <ul className="space-y-1">
          {conversations.map((conversation) => {
            const active = conversation.id === activeId;
            return (
              <li
                key={conversation.id}
                className={`rounded p-2 text-sm ${active ? "bg-blue-50" : "hover:bg-gray-100"}`}
              >
                <DeleteWithConfirm
                  name={conversation.title}
                  onDelete={() => onDelete(conversation.id)}
                >
                  <button
                    type="button"
                    // Tells screen readers which chat is on screen.
                    aria-current={active ? "true" : undefined}
                    onClick={() => onOpen(conversation.id)}
                    className="block w-full text-left"
                  >
                    <span className={`block truncate ${active ? "font-semibold" : ""}`}>
                      {conversation.title}
                    </span>
                    <span className="text-xs text-gray-600">{formatDate(conversation.created_at)}</span>
                  </button>
                </DeleteWithConfirm>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
