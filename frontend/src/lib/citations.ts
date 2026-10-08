import type { Source } from "../api/types";

/** A piece of an answer: plain text, or a citation that points at a source. */
export type Segment = { kind: "text"; text: string } | { kind: "citation"; source: Source };

// A citation like [3], or a group like [1, 4]. Same pattern as the backend's
// backend/app/rag/citations.py, which already splits groups; old stored
// answers may still contain one, so groups are handled here too.
const CITATION = /\[(\d+(?:\s*,\s*\d+)*)\]/g;

/**
 * Split an answer into text and citation segments, for rendering chips.
 *
 * A number with no matching source (e.g. "[7]" with 5 sources, or "array[0]"
 * in code) stays as plain text, exactly as written: we never drop characters.
 * Neighbouring text is merged into one segment, and newlines are kept.
 */
export function parseAnswer(answer: string, sources: Source[]): Segment[] {
  const byNumber = new Map(sources.map((source) => [source.n, source] as const));
  const segments: Segment[] = [];
  let pendingText = "";
  let position = 0;

  function addCitation(source: Source): void {
    if (pendingText) {
      segments.push({ kind: "text", text: pendingText });
      pendingText = "";
    }
    segments.push({ kind: "citation", source });
  }

  for (const match of answer.matchAll(CITATION)) {
    pendingText += answer.slice(position, match.index);
    position = match.index + match[0].length;

    const numbers = match[1].split(",").map((part) => Number.parseInt(part, 10));
    if (numbers.length === 1) {
      const source = byNumber.get(numbers[0]);
      if (source) {
        addCitation(source);
      } else {
        pendingText += match[0]; // not a citation we know: keep it as written
      }
      continue;
    }
    // A group: one chip per known number, unknown numbers stay as "[n]" text.
    for (const n of numbers) {
      const source = byNumber.get(n);
      if (source) {
        addCitation(source);
      } else {
        pendingText += `[${n}]`;
      }
    }
  }

  pendingText += answer.slice(position);
  if (pendingText) {
    segments.push({ kind: "text", text: pendingText });
  }
  return segments;
}
