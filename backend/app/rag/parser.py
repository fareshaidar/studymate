from dataclasses import dataclass
from pathlib import Path

import pymupdf


@dataclass
class Page:
    """The text of one PDF page, with its real page number (starting at 1)."""

    number: int
    text: str


def count_pages(pdf_path: Path) -> int:
    """Total number of pages in a PDF, including blank ones."""
    with pymupdf.open(pdf_path) as doc:
        return len(doc)


def extract_pages(pdf_path: Path) -> list[Page]:
    """Extract text from each page of a PDF.

    Pages with no extractable text (blank pages, or scanned images) are skipped,
    but the remaining pages keep their real page numbers so citations stay correct.
    """
    pages: list[Page] = []
    with pymupdf.open(pdf_path) as doc:
        for index, page in enumerate(doc, start=1):
            text = page.get_text().strip()
            if text:
                pages.append(Page(number=index, text=text))
    return pages