"""Choosing which documents and chunks a request works on. Shared by chat and the study tools."""

from collections.abc import Sequence
from dataclasses import replace
from typing import Protocol, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Document
from app.rag.text_quality import alnum_ratio, strip_diagram_chars


class UnknownDocumentError(LookupError):
    """The request was limited to document ids that don't exist."""

    def __init__(self, missing: list[str]):
        super().__init__(f"Document not found: {', '.join(missing)}")
        self.missing = missing


def resolve_documents(session: Session, document_ids: list[str] | None) -> dict[str, str]:
    """document_id -> filename for the selected documents, newest first.

    None or an empty list means all documents. Raises UnknownDocumentError if
    any requested id doesn't exist, so a typo isn't silently ignored.
    """
    document_ids = document_ids or None
    query = select(Document.id, Document.filename).order_by(Document.created_at.desc())
    if document_ids is not None:
        query = query.where(Document.id.in_(document_ids))
    filenames = {doc_id: filename for doc_id, filename in session.execute(query)}
    if document_ids:
        missing = [d for d in document_ids if d not in filenames]
        if missing:
            raise UnknownDocumentError(missing)
    return filenames


def is_usable(text: str) -> bool:
    """False for chunks that are mostly symbols (e.g. text diagrams), which are noise for the model."""
    return alnum_ratio(text) >= settings.min_alnum_ratio


class _HasText(Protocol):
    text: str


C = TypeVar("C", bound=_HasText)


def usable(chunks: Sequence[C]) -> list[C]:
    """The usable chunks, with diagram characters stripped from their text."""
    return [replace(c, text=strip_diagram_chars(c.text)) for c in chunks if is_usable(c.text)]


T = TypeVar("T")


def evenly_spaced(items: Sequence[T], n: int) -> list[T]:
    """n items taken at evenly spaced positions, in their original order.

    Used when there is more material than we can send: it keeps a sample of the
    whole document instead of only its beginning.
    """
    if n >= len(items):
        return list(items)
    if n <= 0:
        return []
    # Take the middle of each of n equal slices, e.g. 10 items, n=2 -> positions 2 and 7.
    return [items[int((i + 0.5) * len(items) / n)] for i in range(n)]
