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
