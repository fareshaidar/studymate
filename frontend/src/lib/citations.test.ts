import { describe, expect, it } from "vitest";

import type { Source } from "../api/types";
import { parseAnswer, type Segment } from "./citations";

function source(n: number): Source {
  return {
    n,
    document_id: "d1",
    filename: "biology.pdf",
    page: n + 3,
    snippet: `passage ${n}`,
    score: 0.8,
    cited: true,
  };
}

const sources = [source(1), source(2), source(3)];

/** A compact view of the segments: text as-is, citations as their number. */
function shape(segments: Segment[]): (string | number)[] {
  return segments.map((s) => (s.kind === "text" ? s.text : s.source.n));
}

/** Rebuild the answer from its segments, writing citations back as [n]. */
function rebuild(segments: Segment[]): string {
  return segments.map((s) => (s.kind === "text" ? s.text : `[${s.source.n}]`)).join("");
}

describe("parseAnswer", () => {
  it("returns plain text as one segment", () => {
    expect(shape(parseAnswer("No citations here.", sources))).toEqual(["No citations here."]);
  });

  it("returns nothing for an empty answer", () => {
    expect(parseAnswer("", sources)).toEqual([]);
  });

  it("finds citations mid-sentence and at the end", () => {
    const segments = parseAnswer("Cells divide [1] by mitosis [2].", sources);

    expect(shape(segments)).toEqual(["Cells divide ", 1, " by mitosis ", 2, "."]);
    expect(segments[1]).toEqual({ kind: "citation", source: sources[0] });
  });

  it("handles adjacent citations", () => {
    expect(shape(parseAnswer("Both agree [1][3].", sources))).toEqual(["Both agree ", 1, 3, "."]);
  });

  it("splits a group into one citation per number", () => {
    expect(shape(parseAnswer("See [1, 3].", sources))).toEqual(["See ", 1, 3, "."]);
  });

  it("keeps numbers without a source as plain text", () => {
    expect(shape(parseAnswer("Odd [7] and array[0] here [2].", sources))).toEqual([
      "Odd [7] and array[0] here ",
      2,
      ".",
    ]);
  });

  it("keeps an unknown number inside a group as text", () => {
    expect(shape(parseAnswer("See [1, 9].", sources))).toEqual(["See ", 1, "[9]."]);
  });

  it("keeps newlines", () => {
    expect(shape(parseAnswer("First [1].\n\n- second [2]", sources))).toEqual([
      "First ",
      1,
      ".\n\n- second ",
      2,
    ]);
  });

  it("loses no characters", () => {
    const answer = "A [1], b [2]; c [3]! Unknown [4] and [x] stay.\nEnd [1]";

    expect(rebuild(parseAnswer(answer, sources))).toBe(answer);
  });
});
