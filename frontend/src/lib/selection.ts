import { useEffect, useState } from "react";

import type { DocumentInfo } from "../api/types";

/**
 * The selection key for a chat that has not been sent yet. When /chat returns
 * the new conversation's id, moveSelection("new", id) carries the ticks over.
 */
export const NEW_CONVERSATION_KEY = "new";

const STORAGE_PREFIX = "studymate.selection.";

function storageKey(conversationKey: string): string {
  return STORAGE_PREFIX + conversationKey;
}

/**
 * The document ids ticked for one conversation. An empty list means "search all documents".
 *
 * localStorage can be blocked (private windows, strict settings) or hold
 * corrupt data, so any problem falls back to an empty selection.
 */
export function loadSelection(conversationKey: string): string[] {
  try {
    const raw = localStorage.getItem(storageKey(conversationKey));
    if (raw === null) {
      return [];
    }
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed.filter((id): id is string => typeof id === "string");
  } catch {
    return [];
  }
}

/** Save the ticked ids for one conversation; silently does nothing if storage is blocked. */
export function saveSelection(conversationKey: string, ids: string[]): void {
  try {
    localStorage.setItem(storageKey(conversationKey), JSON.stringify(ids));
  } catch {
    // Storage unavailable: the selection still works, it just won't survive a reload.
  }
}

/** Move a selection to another key, e.g. from "new" to the id the backend assigned. */
export function moveSelection(fromKey: string, toKey: string): void {
  saveSelection(toKey, loadSelection(fromKey));
  try {
    localStorage.removeItem(storageKey(fromKey));
  } catch {
    // Nothing to clean up if storage is unavailable.
  }
}

/**
 * React state for the ticked documents of one conversation, saved on every change.
 *
 * Ids of documents that no longer exist (deleted here or in another tab) are
 * hidden from the result; they leave storage the next time the selection changes.
 * While `documents` is still null (not loaded) every stored id is kept, because
 * we cannot tell yet which ones are stale.
 */
export function useSelection(
  conversationKey: string,
  documents: DocumentInfo[] | null,
): [string[], (ids: string[]) => void] {
  const [storedIds, setStoredIds] = useState<string[]>(() => loadSelection(conversationKey));

  // Switching conversations shows that conversation's own selection.
  useEffect(() => {
    setStoredIds(loadSelection(conversationKey));
  }, [conversationKey]);

  function setSelectedIds(ids: string[]): void {
    setStoredIds(ids);
    saveSelection(conversationKey, ids);
  }

  const selectedIds =
    documents === null
      ? storedIds
      : storedIds.filter((id) => documents.some((doc) => doc.id === id));
  return [selectedIds, setSelectedIds];
}
