/**
 * Write page numbers compactly: [1, 2, 3, 5, 9, 10] -> "1–3, 5, 9–10".
 *
 * A summary of a long PDF can use hundreds of pages; ranges keep that readable.
 * Input may be unsorted or contain duplicates.
 */
export function formatPageRanges(pages: number[]): string {
  const sorted = [...new Set(pages)].sort((a, b) => a - b);
  const ranges: string[] = [];
  let start = 0; // index in `sorted` where the current run of consecutive pages starts

  for (let i = 1; i <= sorted.length; i++) {
    // A run ends at the end of the list or where the next page is not consecutive.
    if (i === sorted.length || sorted[i] !== sorted[i - 1] + 1) {
      const first = sorted[start];
      const last = sorted[i - 1];
      ranges.push(first === last ? `${first}` : `${first}–${last}`);
      start = i;
    }
  }
  return ranges.join(", ");
}
