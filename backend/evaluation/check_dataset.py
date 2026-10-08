"""Check the dataset's ground truth against the PDFs, and write a review sheet for a human.

What is checked automatically:
- every document file exists and is exactly the file the dataset was written from;
- every expected page exists and has text;
- every expected page contains at least one of the item's evidence quotes.
Other pages that contain a quote are listed as "maybe also": they could hold the
answer too, and then belong in `pages`. Whether a question is really unanswerable
can't be checked automatically; that is what the review sheet is for.

Usage (from backend/): python -m evaluation.check_dataset [--dataset F] [--documents DIR] [--review F]
"""

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from app.rag.parser import extract_pages
from evaluation.dataset import (
    DEFAULT_DATASET,
    DEFAULT_DOCUMENTS_DIR,
    EVAL_DIR,
    DocumentFileError,
    EvalDataset,
    EvalItem,
    document_path,
    load_dataset,
)

DEFAULT_REVIEW = EVAL_DIR / "results" / "review.md"  # git-ignored: it quotes the PDFs
EXCERPT_CHARS = 300


def normalise(text: str) -> str:
    """Lowercase, letters and digits only, single spaces.

    So a quote still matches when the PDF has other line breaks, punctuation or spacing.
    """
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


@dataclass
class CheckResult:
    problems: list[str] = field(default_factory=list)
    # item id -> other pages whose text also contains an evidence quote
    maybe_also: dict[str, list[int]] = field(default_factory=dict)
    # document id -> page number -> page text (pages without text are absent)
    pages: dict[str, dict[int, str]] = field(default_factory=dict)


def check_dataset(dataset: EvalDataset, documents_dir: Path) -> CheckResult:
    result = CheckResult()
    for doc in dataset.documents:
        try:
            path = document_path(doc, documents_dir)
        except DocumentFileError as exc:
            result.problems.append(str(exc))
            continue
        result.pages[doc.id] = {p.number: p.text for p in extract_pages(path)}

    for item in dataset.items:
        if item.document in result.pages:
            _check_item(item, result.pages[item.document], result)
    return result


def _check_item(item: EvalItem, pages: dict[int, str], result: CheckResult) -> None:
    quotes = [normalise(q) for q in item.evidence]
    if not all(quotes):
        result.problems.append(f"{item.id}: an evidence quote has no letters or digits")
        return

    def has_evidence(text: str) -> bool:
        page = normalise(text)
        return any(q in page for q in quotes)

    for page in item.pages:
        if page not in pages:
            result.problems.append(f"{item.id}: page {page} doesn't exist or has no text")
        elif not has_evidence(pages[page]):
            result.problems.append(f"{item.id}: no evidence quote found on page {page}")
    others = [n for n, text in pages.items() if n not in item.pages and has_evidence(text)]
    if others:
        result.maybe_also[item.id] = others


def write_review(dataset: EvalDataset, result: CheckResult, path: Path) -> None:
    """A markdown sheet with each question next to the page text it is checked against."""
    lines = ["# Dataset review", "", f"{len(dataset.items)} items.", ""]
    if result.problems:
        lines += ["## Problems", ""] + [f"- {p}" for p in result.problems] + [""]
    for item in dataset.items:
        lines += [f"## {item.id} ({item.type}, by {item.author})", "", f"**Q:** {item.question}", ""]
        for turn in item.history:
            lines.append(f"> {turn.role}: {turn.content}")
        if item.expected_standalone:
            lines += ["", f"**Expected standalone:** {item.expected_standalone}"]
        lines += ["", f"**Reference answer:** {item.reference_answer}", ""]
        if item.document:
            lines += [f"**Expected:** {item.document}, pages {item.pages}", ""]
            lines += ["**Evidence:** " + " / ".join(f'"{q}"' for q in item.evidence), ""]
            if item.id in result.maybe_also:
                lines += [f"**Maybe also on pages:** {result.maybe_also[item.id]}", ""]
            for page in item.pages:
                text = result.pages.get(item.document, {}).get(page, "")
                lines += [f"Page {page}: …{_excerpt(text, item.evidence)}…", ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _excerpt(page_text: str, evidence: list[str]) -> str:
    """The page text around the first evidence quote found on it (or its start), on one line."""
    flat = " ".join(page_text.split())
    start = 0
    for quote in evidence:
        found = flat.find(quote.split()[0])
        if found >= 0:
            start = max(found - EXCERPT_CHARS // 3, 0)
            break
    return flat[start : start + EXCERPT_CHARS]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--documents", type=Path, default=DEFAULT_DOCUMENTS_DIR)
    parser.add_argument("--review", type=Path, default=DEFAULT_REVIEW)
    args = parser.parse_args(argv)

    dataset = load_dataset(args.dataset)
    result = check_dataset(dataset, args.documents)
    write_review(dataset, result, args.review)

    counts = {t: sum(i.type == t for i in dataset.items) for t in sorted({i.type for i in dataset.items})}
    print(f"{len(dataset.items)} items: {counts}")
    for item_id, pages in result.maybe_also.items():
        print(f"note: {item_id} evidence also on pages {pages}")
    for problem in result.problems:
        print(f"PROBLEM: {problem}")
    print(f"Review sheet: {args.review}")
    return 1 if result.problems else 0


if __name__ == "__main__":
    sys.exit(main())
