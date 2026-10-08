"""Choosing which documents and chunks a request works on. Shared by chat and the study tools."""

from collections.abc import Sequence
from dataclasses import replace
from typing import Protocol, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Document
from app.rag.text_quality import alnum_ratio, is_front_matter, strip_diagram_chars
from app.rag.vectorstore import SearchResult, StoredChunk, VectorStore


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
    """False for chunks that are noise for the model: mostly symbols (e.g. text diagrams),
    or, when exclude_front_matter is on, a table of contents or list of figures.

    Used by chat retrieval, the study tools and the evaluation, so all three agree.
    """
    if alnum_ratio(text) < settings.min_alnum_ratio:
        return False
    return not (settings.exclude_front_matter and is_front_matter(text))


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


def select_passages(
    document_ids: list[str],
    topic: str | None,
    limit: int,
    store: VectorStore,
) -> list[StoredChunk | SearchResult]:
    """Up to `limit` usable chunks to build a quiz or flashcards from.

    With a topic: the chunks most similar to it (above `min_similarity`), best first.
    Without one: each document gets an equal share, spread evenly through it, so
    one long document can't crowd out a short one. A share a short document can't
    fill is simply left unused (kept simple on purpose).
    """
    if not document_ids:
        # Also needed for the search below: an empty list there would mean "all chunks",
        # including orphan chunks of deleted documents.
        return []
    if topic:
        results = store.search(topic, k=limit * 2, document_ids=document_ids)
        relevant = [r for r in results if r.score >= settings.min_similarity]
        return usable(relevant)[:limit]

    passages: list[StoredChunk | SearchResult] = []
    share, extra = divmod(limit, len(document_ids))
    for i, doc_id in enumerate(document_ids):
        n = share + (1 if i < extra else 0)
        passages.extend(evenly_spaced(usable(store.get_chunks(doc_id)), n))
    return passages
