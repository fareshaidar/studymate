import { describe, expect, it } from "vitest";

import { formatPageRanges } from "./pages";

describe("formatPageRanges", () => {
  it("writes a single page as itself", () => {
    expect(formatPageRanges([7])).toBe("7");
  });

  it("joins consecutive pages into ranges", () => {
    expect(formatPageRanges([1, 2, 3, 5, 9, 10])).toBe("1–3, 5, 9–10");
  });

  it("sorts and removes duplicates first", () => {
    expect(formatPageRanges([4, 2, 3, 3, 8])).toBe("2–4, 8");
  });

  it("returns an empty string for no pages", () => {
    expect(formatPageRanges([])).toBe("");
  });
});
