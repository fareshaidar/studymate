from dataclasses import dataclass
from pathlib import Path

import pymupdf


@dataclass
class Page:
    """The text of one PDF page, with its real page number (starting at 1)."""

    number: int
    text: str


def _open(pdf_path: Path) -> pymupdf.Document:
    """Open a PDF from its bytes rather than by file name.

    If PyMuPDF fails while opening a damaged file by name, it can keep that file open
    until garbage collection, and on Windows an open file can't be deleted: the upload
    endpoint's cleanup then failed. Opening from bytes never holds the file. Uploads
    are at most max_upload_mb, so reading them into memory is fine.
    """
    return pymupdf.open(stream=pdf_path.read_bytes(), filetype="pdf")


def needs_password(pdf_path: Path) -> bool:
    """True for a password-protected PDF, whose pages can't be read without the password."""
    with _open(pdf_path) as doc:
        return bool(doc.needs_pass)


def count_pages(pdf_path: Path) -> int:
    """Total number of pages in a PDF, including blank ones."""
    with _open(pdf_path) as doc:
        return len(doc)


def extract_pages(pdf_path: Path) -> list[Page]:
    """Extract text from each page of a PDF.

    Pages with no extractable text (blank pages, or scanned images) are skipped,
    but the remaining pages keep their real page numbers so citations stay correct.
    """
    pages: list[Page] = []
    with _open(pdf_path) as doc:
        for index, page in enumerate(doc, start=1):
            text = page.get_text().strip()
            if text:
                pages.append(Page(number=index, text=text))
    return pages
