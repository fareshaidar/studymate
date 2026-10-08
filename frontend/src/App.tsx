import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { errorMessage } from "./api/client";
import { deleteConversation, getConversation, listConversations } from "./api/conversations";
import { listDocuments } from "./api/documents";
import { ApiError, type ConversationSummary, type DocumentInfo } from "./api/types";
import { ChatView } from "./components/chat/ChatView";
import type { ChatMessage } from "./components/chat/MessageList";
import { BackendStatus } from "./components/common/BackendStatus";
import { ErrorNotice } from "./components/common/ErrorNotice";
import { ConversationList } from "./components/conversations/ConversationList";
import { DocumentPanel } from "./components/documents/DocumentPanel";
import { fromStoredMessages } from "./lib/messages";
import {
  forgetSelection,
  moveSelection,
  NEW_CONVERSATION_KEY,
  useSelection,
} from "./lib/selection";

/** A conversation that failed to open, kept so Retry knows which one. */
interface FailedOpen {
  id: string;
  error: ApiError;
}

/**
 * The whole page: a sidebar (documents, conversations) and a main area with the chat.
 *
 * The lists, the selection and the current conversation live here, not in the
 * sidebar or the chat, because both of those (and the study tools in a later
 * step) need them.
 */
export default function App() {
  const [documents, setDocuments] = useState<DocumentInfo[] | null>(null);
  const [documentsError, setDocumentsError] = useState<string | null>(null);
  const [conversations, setConversations] = useState<ConversationSummary[] | null>(null);
  const [conversationsError, setConversationsError] = useState<string | null>(null);

  // null for a new chat, until its first answer gives us the conversation id.
  const [conversationId, setConversationId] = useState<string | null>(null);
  // The saved messages of a reopened conversation, handed to a fresh ChatView.
  const [initialMessages, setInitialMessages] = useState<ChatMessage[]>([]);
  // Used as ChatView's key: changing it gives a fresh chat (empty or reopened).
  const [chatSession, setChatSession] = useState(0);
  const [opening, setOpening] = useState(false);
  const [failedOpen, setFailedOpen] = useState<FailedOpen | null>(null);
  // Counts open requests, so only the most recent click's result is used.
  const latestOpen = useRef(0);

  const [selectedIds, setSelectedIds] = useSelection(
    conversationId ?? NEW_CONVERSATION_KEY,
    documents,
  );
  // Recomputed only when the list changes, not on every render.
  const existingDocumentIds = useMemo(
    () => (documents ? new Set(documents.map((doc) => doc.id)) : undefined),
    [documents],
  );

  const refreshDocuments = useCallback(async (): Promise<void> => {
    try {
      setDocuments(await listDocuments());
      setDocumentsError(null);
    } catch (err) {
      setDocumentsError(errorMessage(err));
    }
  }, []);

  const refreshConversations = useCallback(async (): Promise<void> => {
    try {
      setConversations(await listConversations());
      setConversationsError(null);
    } catch (err) {
      setConversationsError(errorMessage(err));
    }
  }, []);

  useEffect(() => {
    void refreshDocuments();
    void refreshConversations();
  }, [refreshDocuments, refreshConversations]);

  function showChat(id: string | null, messages: ChatMessage[]): void {
    setConversationId(id);
    setInitialMessages(messages);
    setFailedOpen(null);
    setChatSession((n) => n + 1);
  }

  function handleNewChat(): void {
    latestOpen.current++; // a slower open still in flight must not replace the new chat
    setOpening(false);
    showChat(null, []);
  }

  async function handleOpen(id: string): Promise<void> {
    if (id === conversationId && !failedOpen) {
      return; // already on screen
    }
    const request = ++latestOpen.current;
    setOpening(true);
    setFailedOpen(null);
    try {
      const detail = await getConversation(id);
      if (request === latestOpen.current) {
        showChat(id, fromStoredMessages(detail.messages));
      }
    } catch (err) {
      if (request === latestOpen.current) {
        const error = err instanceof ApiError ? err : new ApiError(0, errorMessage(err));
        setFailedOpen({ id, error });
        // A 404 means it was deleted elsewhere: refresh so it leaves the list.
        void refreshConversations();
      }
    } finally {
      if (request === latestOpen.current) {
        setOpening(false);
      }
    }
  }

  function handleConversationStarted(id: string): void {
    // Move the ticks first, so the selection hook finds them under the new key.
    moveSelection(NEW_CONVERSATION_KEY, id);
    setConversationId(id);
    void refreshConversations(); // the new chat appears at the top of the list
  }

  async function handleDeleteConversation(id: string): Promise<void> {
    await deleteConversation(id); // errors propagate to the row, which shows them
    forgetSelection(id);
    if (id === conversationId) {
      handleNewChat();
    }
    await refreshConversations();
  }

  return (
    <div className="flex h-screen bg-gray-50 text-gray-900">
      <aside className="w-80 shrink-0 space-y-6 overflow-y-auto border-r border-gray-200 bg-white p-4">
        <h1 className="text-xl font-bold">StudyMate</h1>
        <DocumentPanel
          documents={documents}
          listError={documentsError}
          selectedIds={selectedIds}
          onSelectionChange={setSelectedIds}
          onDocumentsChanged={refreshDocuments}
        />
        <ConversationList
          conversations={conversations}
          listError={conversationsError}
          activeId={conversationId}
          onOpen={(id) => void handleOpen(id)}
          onNewChat={handleNewChat}
          onDelete={handleDeleteConversation}
        />
      </aside>
      <main className="flex min-w-0 flex-1 flex-col gap-4 p-6">
        <BackendStatus />
        {failedOpen && (
          <ErrorNotice
            error={failedOpen.error}
            onRetry={() => void handleOpen(failedOpen.id)}
            onNewChat={handleNewChat}
          />
        )}
        {/* The current chat stays mounted while another loads, so a failed open loses nothing. */}
        {opening && (
          <p role="status" className="text-gray-600">
            Loading conversation…
          </p>
        )}
        <ChatView
          key={chatSession}
          documentIds={selectedIds}
          conversationId={conversationId}
          initialMessages={initialMessages}
          existingDocumentIds={existingDocumentIds}
          onConversationStarted={handleConversationStarted}
          onNewChat={handleNewChat}
        />
      </main>
    </div>
  );
}
