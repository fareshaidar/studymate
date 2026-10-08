import { describe, expect, it } from "vitest";

import { stripApiPrefix } from "./proxy";

describe("stripApiPrefix", () => {
  it("removes the /api prefix", () => {
    expect(stripApiPrefix("/api/documents")).toBe("/documents");
    expect(stripApiPrefix("/api/health")).toBe("/health");
  });

  it("keeps the rest of the path and the query string", () => {
    expect(stripApiPrefix("/api/documents/abc-123/file")).toBe("/documents/abc-123/file");
    expect(stripApiPrefix("/api/conversations?limit=5")).toBe("/conversations?limit=5");
  });

  it("maps a bare /api to the backend root", () => {
    expect(stripApiPrefix("/api")).toBe("/");
  });

  it("leaves paths that only start with the letters 'api' alone", () => {
    expect(stripApiPrefix("/apiary")).toBe("/apiary");
    expect(stripApiPrefix("/documents")).toBe("/documents");
  });
});
