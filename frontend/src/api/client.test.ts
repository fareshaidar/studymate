import { describe, expect, it, vi } from "vitest";

import { OFFLINE_MESSAGE, request } from "./client";
import { ApiError } from "./types";

/** Replace the global fetch with one that returns a single canned response. */
function mockFetch(body: string | null, status: number, headers: Record<string, string> = {}) {
  const fetchMock = vi.fn().mockResolvedValue(new Response(body, { status, headers }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

/** Run a request that should fail and return the ApiError it threw. */
async function catchApiError(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise;
  } catch (err) {
    expect(err).toBeInstanceOf(ApiError);
    return err as ApiError;
  }
  throw new Error("expected the request to fail");
}

describe("request", () => {
  it("adds the /api prefix and returns the parsed JSON", async () => {
    const fetchMock = mockFetch('{"status":"ok"}', 200);

    await expect(request("/health")).resolves.toEqual({ status: "ok" });
    expect(fetchMock).toHaveBeenCalledWith("/api/health", undefined);
  });

  it("returns undefined for 204 No Content", async () => {
    mockFetch(null, 204); // a 204 response must have a null body
    await expect(request("/documents/x", { method: "DELETE" })).resolves.toBeUndefined();
  });

  it("uses a string detail as the message", async () => {
    mockFetch('{"detail":"Only PDF files are supported."}', 400);

    const error = await catchApiError(request("/documents"));
    expect(error.status).toBe(400);
    expect(error.message).toBe("Only PDF files are supported.");
    expect(error.retryAfter).toBeUndefined();
  });

  it("turns a FastAPI 422 list into one sentence", async () => {
    mockFetch(
      JSON.stringify({
        detail: [
          { loc: ["body", "question"], msg: "Field required", type: "missing" },
          { loc: ["body", "num_questions"], msg: "Input should be less than or equal to 10" },
        ],
      }),
      422,
    );

    const error = await catchApiError(request("/chat"));
    expect(error.status).toBe(422);
    expect(error.message).toBe(
      "question: Field required; num_questions: Input should be less than or equal to 10",
    );
  });

  it("reads Retry-After on a 503", async () => {
    mockFetch('{"detail":"The model is busy."}', 503, { "Retry-After": "12" });

    const error = await catchApiError(request("/chat"));
    expect(error.status).toBe(503);
    expect(error.message).toBe("The model is busy.");
    expect(error.retryAfter).toBe(12);
  });

  it("falls back to a generic message when the body is not JSON", async () => {
    mockFetch("Internal Server Error", 500);

    const error = await catchApiError(request("/health"));
    expect(error.status).toBe(500);
    expect(error.message).toBe("Request failed (HTTP 500).");
  });

  it("reports status 0 when the backend cannot be reached", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    const error = await catchApiError(request("/health"));
    expect(error.status).toBe(0);
    expect(error.message).toBe(OFFLINE_MESSAGE);
  });
});
