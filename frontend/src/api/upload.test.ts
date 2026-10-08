import { describe, expect, it, vi } from "vitest";

import { OFFLINE_MESSAGE } from "./client";
import { ApiError } from "./types";
import { uploadDocument, type UploadProgress } from "./upload";

/**
 * A minimal stand-in for XMLHttpRequest. Tests drive it by hand: fire progress,
 * finish the upload, then answer with a status and body.
 */
class FakeXhr {
  static last: FakeXhr;

  method = "";
  url = "";
  sentBody: unknown = null;
  status = 0;
  responseText = "";
  responseHeaders: Record<string, string> = {};
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  upload: {
    onprogress: ((event: { lengthComputable: boolean; loaded: number; total: number }) => void) | null;
    onload: (() => void) | null;
  } = { onprogress: null, onload: null };

  constructor() {
    FakeXhr.last = this;
  }

  open(method: string, url: string): void {
    this.method = method;
    this.url = url;
  }

  send(body: unknown): void {
    this.sentBody = body;
  }

  getResponseHeader(name: string): string | null {
    return this.responseHeaders[name] ?? null;
  }

  respond(status: number, body: string, headers: Record<string, string> = {}): void {
    this.status = status;
    this.responseText = body;
    this.responseHeaders = headers;
    this.onload?.();
  }
}

const pdf = new File(["%PDF-1.7"], "notes.pdf", { type: "application/pdf" });

/** Start an upload with the fake XHR installed and collect the progress events. */
function startUpload() {
  vi.stubGlobal("XMLHttpRequest", FakeXhr);
  const events: UploadProgress[] = [];
  const promise = uploadDocument(pdf, (progress) => events.push(progress));
  return { promise, events, xhr: FakeXhr.last };
}

async function catchApiError(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise;
  } catch (err) {
    expect(err).toBeInstanceOf(ApiError);
    return err as ApiError;
  }
  throw new Error("expected the upload to fail");
}

describe("uploadDocument", () => {
  it("posts the file as multipart form data to /api/documents", () => {
    const { xhr } = startUpload();

    expect(xhr.method).toBe("POST");
    expect(xhr.url).toBe("/api/documents");
    expect(xhr.sentBody).toBeInstanceOf(FormData);
    expect((xhr.sentBody as FormData).get("file")).toBeInstanceOf(File);
  });

  it("reports bytes sent, then indexing, then resolves with the document", async () => {
    const { promise, events, xhr } = startUpload();

    xhr.upload.onprogress?.({ lengthComputable: true, loaded: 50, total: 200 });
    xhr.upload.onprogress?.({ lengthComputable: true, loaded: 200, total: 200 });
    xhr.upload.onload?.();
    const doc = { id: "d1", filename: "notes.pdf", page_count: 3, chunk_count: 9, created_at: "2026-10-08T10:00:00" };
    xhr.respond(201, JSON.stringify(doc));

    await expect(promise).resolves.toEqual(doc);
    expect(events).toEqual([
      { phase: "uploading", loaded: 50, total: 200 },
      { phase: "uploading", loaded: 200, total: 200 },
      { phase: "indexing" },
    ]);
  });

  it("ignores progress events without a known total", () => {
    const { events, xhr } = startUpload();

    xhr.upload.onprogress?.({ lengthComputable: false, loaded: 10, total: 0 });

    expect(events).toEqual([]);
  });

  it.each([
    [400, "Only PDF files are supported."],
    [413, "File is larger than 50 MB."],
    [422, "No text could be extracted from this PDF."],
  ])("rejects with the backend's message on %i", async (status, detail) => {
    const { promise, xhr } = startUpload();

    xhr.respond(status, JSON.stringify({ detail }));

    const error = await catchApiError(promise);
    expect(error.status).toBe(status);
    expect(error.message).toBe(detail);
  });

  it("reports status 0 on a network error", async () => {
    const { promise, xhr } = startUpload();

    xhr.onerror?.();

    const error = await catchApiError(promise);
    expect(error.status).toBe(0);
    expect(error.message).toBe(OFFLINE_MESSAGE);
  });
});
