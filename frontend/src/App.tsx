import { useCallback, useEffect, useState } from "react";

import { errorMessage } from "./api/client";
import { listDocuments } from "./api/documents";
import type { DocumentInfo } from "./api/types";
import { ChatView } from "./components/chat/ChatView";
import { BackendStatus } from "./components/common/BackendStatus";
import { DocumentPanel } from "./components/documents/DocumentPanel";
import { moveSelection, NEW_CONVERSATION_KEY, useSelection } from "./lib/selection";

/**
 * The whole page: a sidebar for documents and a main area with the chat.
 *
 * The document list, the selection and the current conversation live here,
 * not in the sidebar or the chat, because both of those (and the study tools
 * in a later step) need them.
 */
export default function App() {
  const [documents, setDocuments] = useState<DocumentInfo[] | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  // null until the first answer of a new chat gives us the conversation id.
  const [conversationId, setConversationId] = useState<string | null>(null);
  // Used as ChatView's key: changing it gives a fresh, empty chat.
  const [chatSession, setChatSession] = useState(0);
  const [selectedIds, setSelectedIds] = useSelection(
    conversationId ?? NEW_CONVERSATION_KEY,
    documents,
  );

  const refreshDocuments = useCallback(async (): Promise<void> => {
    try {
      setDocuments(await listDocuments());
      setListError(null);
    } catch (err) {
      setListError(errorMessage(err));
    }
  }, []);

  useEffect(() => {
    void refreshDocuments();
  }, [refreshDocuments]);

  function handleConversationStarted(id: string): void {
    // Move the ticks first, so the selection hook finds them under the new key.
    moveSelection(NEW_CONVERSATION_KEY, id);
    setConversationId(id);
  }

  function handleNewChat(): void {
    setConversationId(null);
    setChatSession((n) => n + 1);
  }

  return (
    <div className="flex h-screen bg-gray-50 text-gray-900">
      <aside className="w-80 shrink-0 space-y-4 overflow-y-auto border-r border-gray-200 bg-white p-4">
        <h1 className="text-xl font-bold">StudyMate</h1>
        <DocumentPanel
          documents={documents}
          listError={listError}
          selectedIds={selectedIds}
          onSelectionChange={setSelectedIds}
          onDocumentsChanged={refreshDocuments}
        />
      </aside>
      <main className="flex min-w-0 flex-1 flex-col gap-4 p-6">
        <BackendStatus />
        <ChatView
          key={chatSession}
          documentIds={selectedIds}
          conversationId={conversationId}
          onConversationStarted={handleConversationStarted}
          onNewChat={handleNewChat}
        />
      </main>
    </div>
  );
}
