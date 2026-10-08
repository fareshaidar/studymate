import { API_PREFIX } from "../proxy";
import { request } from "./client";
import type { DocumentInfo, Health } from "./types";

/** GET /health: resolves when the backend is up, throws ApiError otherwise. */
export function getHealth(): Promise<Health> {
  return request<Health>("/health");
}

/** GET /documents: all uploaded PDFs, newest first. */
export function listDocuments(): Promise<DocumentInfo[]> {
  return request<DocumentInfo[]>("/documents");
}

/** DELETE /documents/{id}: removes the row, its chunks and the stored PDF. */
export function deleteDocument(id: string): Promise<void> {
  return request<void>(`/documents/${encodeURIComponent(id)}`, { method: "DELETE" });
}

/**
 * Link that opens a document's PDF at a page, for a new browser tab.
 *
 * Browsers' built-in PDF viewers read "#page=n" (1-based, like our page numbers).
 * The fragment never reaches the server; it only tells the viewer where to scroll.
 */
export function pdfPageUrl(documentId: string, page: number): string {
  return `${API_PREFIX}/documents/${encodeURIComponent(documentId)}/file#page=${page}`;
}
