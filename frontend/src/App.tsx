import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";

import { errorMessage } from "./api/client";
import { deleteConversation, getConversation, listConversations } from "./api/conversations";
import { listDocuments } from "./api/documents";
import { ApiError, type ConversationSummary, type DocumentInfo } from "./api/types";
import { ChatView } from "./components/chat/ChatView";
import type { ChatMessage } from "./components/chat/MessageList";
import { BackendStatus } from "./components/common/BackendStatus";
import { ErrorNotice } from "./components/common/ErrorNotice";
import { tabId, tabPanelId, Tabs, type TabItem } from "./components/common/Tabs";
import { ConversationList } from "./components/conversations/ConversationList";
import { DocumentPanel } from "./components/documents/DocumentPanel";
import { StudyView } from "./components/study/StudyView";
import { fromStoredMessages } from "./lib/messages";
import {
  forgetSelection,
  moveSelection,
  NEW_CONVERSATION_KEY,
  useSelection,
} from "./lib/selection";

type Tab = "chat" | "study";

const TABS: TabItem<Tab>[] = [
  { id: "chat", label: "Chat" },
  { id: "study", label: "Study" },
];

/** A conversation that failed to open, kept so Retry knows which one. */
interface FailedOpen {
  id: string;
  error: ApiError;
}

/**
 * The whole page: a sidebar (documents, conversations) and a main area with
 * the Chat and Study tabs.
 *
 * The lists, the selection and the current conversation live here, not in the
 * sidebar or the tabs, because several of them need the same data.
 */
export default function App() {
  const [tab, setTab] = useState<Tab>("chat");
  // Narrow screens only: whether the sidebar is shown over the page.
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);
  const [documents, setDocuments] = useState<DocumentInfo[] | null>(null);
  const [documentsError, setDocumentsError] = useState<string | null>(null);
  // From /health; null until known (then only the backend checks the size).
  const [maxUploadMb, setMaxUploadMb] = useState<number | null>(null);
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
  // Only once the list has loaded, so the hint doesn't flash while it loads.
  const noDocuments = documents !== null && documents.length === 0;

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

  function closeSidebar(): void {
    setSidebarOpen(false);
    menuButton.current?.focus(); // back to the button that opened it
  }

  function handleSidebarKeyDown(event: KeyboardEvent<HTMLElement>): void {
    if (event.key === "Escape" && sidebarOpen) {
      closeSidebar();
    }
  }

  function handleBackOnline(): void {
    // The backend was started after the page loaded: fetch what we couldn't before.
    void refreshDocuments();
    void refreshConversations();
  }

  return (
    // Narrow screens: a column with a top bar; from Tailwind's md breakpoint (768 px) up, side by side.
    <div className="flex h-screen flex-col bg-gray-50 text-gray-900 md:flex-row">
      <header className="flex items-center justify-between border-b border-gray-200 bg-white px-4 py-2 md:hidden">
        <span className="text-lg font-bold">StudyMate</span>
        <button
          ref={menuButton}
          type="button"
          aria-expanded={sidebarOpen}
          aria-controls="sidebar"
          onClick={() => setSidebarOpen(!sidebarOpen)}
          className="rounded border border-gray-300 px-3 py-1 text-sm"
        >
          Documents &amp; chats
        </button>
      </header>

      <aside
        id="sidebar"
        aria-label="Documents and conversations"
        onKeyDown={handleSidebarKeyDown}
        // Narrow screens: hidden, or a full-screen layer when opened. Wide screens: always shown.
        className={`${sidebarOpen ? "fixed inset-0 z-20 block" : "hidden"} space-y-6 overflow-y-auto border-r border-gray-200 bg-white p-4 md:static md:block md:w-80 md:shrink-0`}
      >
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-bold">StudyMate</h1>
          <button
            type="button"
            onClick={closeSidebar}
            className="rounded border border-gray-300 px-3 py-1 text-sm md:hidden"
          >
            Close
          </button>
        </div>
        <DocumentPanel
          documents={documents}
          listError={documentsError}
          selectedIds={selectedIds}
          onSelectionChange={setSelectedIds}
          onDocumentsChanged={refreshDocuments}
          maxUploadMb={maxUploadMb}
        />
        <ConversationList
          conversations={conversations}
          listError={conversationsError}
          activeId={conversationId}
          onOpen={(id) => {
            setSidebarOpen(false); // on narrow screens, show the chat that was picked
            void handleOpen(id);
          }}
          onNewChat={() => {
            setSidebarOpen(false);
            handleNewChat();
          }}
          onDelete={handleDeleteConversation}
        />
      </aside>
      <main className="flex min-h-0 min-w-0 flex-1 flex-col gap-4 p-4 md:p-6">
        {/* For heading navigation in screen readers; the tabs already show it visually. */}
        <h2 className="sr-only">{tab === "chat" ? "Chat" : "Study"}</h2>
        <BackendStatus
          onBackOnline={handleBackOnline}
          onHealth={(health) => setMaxUploadMb(health.max_upload_mb ?? null)}
        />
        <Tabs label="Main view" tabs={TABS} selected={tab} onSelect={setTab} idPrefix="main" />

        {/* Both panels stay mounted and the inactive one is hidden: unmounting would
            drop an answer still loading in the chat, or a quiz in progress. */}
        <section
          id={tabPanelId("main", "chat")}
          role="tabpanel"
          aria-labelledby={tabId("main", "chat")}
          hidden={tab !== "chat"}
          className="flex min-h-0 flex-1 flex-col gap-4"
        >
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
            noDocuments={noDocuments}
            onConversationStarted={handleConversationStarted}
            onNewChat={handleNewChat}
          />
        </section>
        <section
          id={tabPanelId("main", "study")}
          role="tabpanel"
          aria-labelledby={tabId("main", "study")}
          hidden={tab !== "study"}
          className="min-h-0 flex-1 overflow-y-auto"
        >
          <StudyView
            documentIds={selectedIds}
            documentCount={documents?.length ?? 0}
            noDocuments={noDocuments}
          />
        </section>
      </main>
    </div>
  );
}
