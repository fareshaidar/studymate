import { describe, expect, it } from "vitest";

import { pdfPageUrl } from "./documents";

describe("pdfPageUrl", () => {
  it("points at the file endpoint with a #page fragment", () => {
    expect(pdfPageUrl("d1", 4)).toBe("/api/documents/d1/file#page=4");
  });

  it("encodes the document id", () => {
    expect(pdfPageUrl("a/b c", 1)).toBe("/api/documents/a%2Fb%20c/file#page=1");
  });
});
