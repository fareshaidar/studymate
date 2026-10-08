import { useCallback, useEffect, useState } from "react";

import { errorMessage } from "./api/client";
import { listDocuments } from "./api/documents";
import type { DocumentInfo } from "./api/types";
import { BackendStatus } from "./components/common/BackendStatus";
import { DocumentPanel } from "./components/documents/DocumentPanel";
import { NEW_CONVERSATION_KEY, useSelection } from "./lib/selection";

/**
 * The whole page: a sidebar for documents and a main area.
 *
 * The document list and the selection live here, not in the sidebar, because
 * the chat and study tools (later steps) need them too.
 */
export default function App() {
  const [documents, setDocuments] = useState<DocumentInfo[] | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  // Only the not-yet-sent chat exists until conversations arrive in step 5.
  const [selectedIds, setSelectedIds] = useSelection(NEW_CONVERSATION_KEY, documents);

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

  return (
    <div className="flex min-h-screen bg-gray-50 text-gray-900">
      <aside className="w-80 shrink-0 space-y-4 border-r border-gray-200 bg-white p-4">
        <h1 className="text-xl font-bold">StudyMate</h1>
        <DocumentPanel
          documents={documents}
          listError={listError}
          selectedIds={selectedIds}
          onSelectionChange={setSelectedIds}
          onDocumentsChanged={refreshDocuments}
        />
      </aside>
      <main className="flex-1 space-y-4 p-6">
        <BackendStatus />
        <p className="text-gray-600">Chat and study tools will appear here.</p>
      </main>
    </div>
  );
}
