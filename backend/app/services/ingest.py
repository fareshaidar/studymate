from pathlib import Path

import pymupdf
from sqlalchemy.orm import Session

from app.db.models import Document, _new_id
from app.rag.chunker import chunk_pages
from app.rag.parser import count_pages, extract_pages
from app.rag.vectorstore import VectorStore


class IngestError(ValueError):
    """The file can't be indexed (not a valid PDF, or no text to extract)."""


def ingest_pdf(
    pdf_path: Path, filename: str, session: Session, store: VectorStore
) -> Document:
    """Parse, chunk and index one PDF, and record it in the database.

    Chroma and SQLite are kept in sync: if either step fails, the chunks are
    removed again so no half-indexed document is left behind.
    """
    try:
        pages = extract_pages(pdf_path)
        page_count = count_pages(pdf_path)
    except pymupdf.FileDataError as exc:
        raise IngestError("The file is not a valid PDF.") from exc

    chunks = chunk_pages(pages)
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
    try:
        store.add_chunks(doc.id, chunks)
        session.add(doc)
        session.commit()
    except Exception:
        session.rollback()
        store.delete_document(doc.id)
        raise
    return doc
