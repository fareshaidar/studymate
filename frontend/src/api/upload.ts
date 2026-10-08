import { API_PREFIX } from "../proxy";
import { buildApiError, OFFLINE_MESSAGE } from "./client";
import { ApiError, type UploadedDocument } from "./types";

/** What the UI shows while an upload runs. */
export type UploadProgress =
  | { phase: "uploading"; loaded: number; total: number }
  | { phase: "indexing" };

/**
 * Upload a PDF to POST /documents, reporting progress along the way.
 *
 * This uses XMLHttpRequest instead of fetch because fetch cannot report how many
 * bytes have been sent. The request has two parts from the user's point of view:
 * sending the file (progress events), then waiting while the backend indexes it
 * synchronously (about a minute for a 400-page PDF) before it answers.
 */
export function uploadDocument(
  file: File,
  onProgress: (progress: UploadProgress) => void,
): Promise<UploadedDocument> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_PREFIX}/documents`);

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        onProgress({ phase: "uploading", loaded: event.loaded, total: event.total });
      }
    };
    // All bytes are sent, but the response only comes after indexing finishes.
    xhr.upload.onload = () => onProgress({ phase: "indexing" });

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText) as UploadedDocument);
      } else {
        reject(buildApiError(xhr.status, xhr.responseText, xhr.getResponseHeader("Retry-After")));
      }
    };
    // onerror fires when no response arrived at all, like a rejected fetch.
    xhr.onerror = () => reject(new ApiError(0, OFFLINE_MESSAGE));

    const form = new FormData();
    form.append("file", file); // the backend's UploadFile parameter is named "file"
    xhr.send(form);
  });
}
