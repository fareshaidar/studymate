import logging
from dataclasses import dataclass
from pathlib import Path

import pymupdf
from sqlalchemy.orm import Session

from app.db.models import Document, _new_id
from app.rag.chunker import chunk_pages
from app.rag.parser import Page, count_pages, extract_pages, needs_password
from app.rag.vectorstore import VectorStore

logger = logging.getLogger(__name__)


class IngestError(ValueError):
    """The file can't be indexed. The message is safe and friendly enough to show a student."""


@dataclass
class IngestResult:
    document: Document
    # Pages with extractable text. The rest are blank or scanned images (not searchable).
    # Not stored in the database (no migrations), so it is only known right after upload.
    text_page_count: int


def _read_pdf(pdf_path: Path) -> tuple[list[Page], int]:
    """The pages with text, and the total page count. Raises IngestError for any file
    that can't be read as a PDF, so the student gets a clear reason instead of a 500."""
    if pdf_path.stat().st_size == 0:
        raise IngestError("The file is empty.")
    try:
        if needs_password(pdf_path):
            raise IngestError(
                "This PDF is password-protected. Remove the password and upload it again."
            )
        return extract_pages(pdf_path), count_pages(pdf_path)
    except IngestError:
        raise
    except pymupdf.FileDataError as exc:  # not a PDF, or damaged beyond repair
        raise IngestError("The file is not a valid PDF.") from exc
    except Exception as exc:
        # Any other PyMuPDF failure while reading. Only the error type goes to the log:
        # the message could contain text from the document.
        logger.warning("Could not read PDF: %s", type(exc).__name__)
        raise IngestError("This PDF could not be read.") from exc


def ingest_pdf(
    pdf_path: Path,
    filename: str,
    session: Session,
    store: VectorStore,
    *,
    max_chars: int = 1800,
    overlap_chars: int = 250,
) -> IngestResult:
    """Parse, chunk and index one PDF, and record it in the database.

    Chroma and SQLite are kept in sync: if either step fails, the chunks are
    removed again so no half-indexed document is left behind. The chunk size
    arguments exist so evaluation can compare sizes; the app uses the defaults.
    """
    pages, page_count = _read_pdf(pdf_path)

    chunks = chunk_pages(pages, max_chars=max_chars, overlap_chars=overlap_chars)
    if not chunks:
        raise IngestError(
            "No text could be extracted from this PDF (is it a scanned image?)."
        )

    doc = Document(
        id=_new_id(),
        filename=filename,
        page_count=page_count,
        chunk_count=len(chunks),
    )
    # The catch-all above covers reading only: a database or Chroma failure here is a
    # real server problem and must not be reported as "this PDF could not be read".
    try:
        store.add_chunks(doc.id, chunks)
        session.add(doc)
        session.commit()
    except Exception:
        session.rollback()
        store.delete_document(doc.id)
        raise
    return IngestResult(document=doc, text_page_count=len(pages))
