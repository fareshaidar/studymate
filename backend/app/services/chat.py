import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Document
from app.llm.base import LLMClient
from app.rag.citations import check_citations
from app.rag.prompts import (
    NOT_FOUND_ANSWER,
    SYSTEM_PROMPT,
    PromptChunk,
    build_prompt,
    is_not_found_answer,
)
from app.rag.vectorstore import SearchResult, VectorStore

logger = logging.getLogger(__name__)

SNIPPET_CHARS = 200


class UnknownDocumentError(LookupError):
    """The question was limited to document ids that don't exist."""

    def __init__(self, missing: list[str]):
        super().__init__(f"Document not found: {', '.join(missing)}")
        self.missing = missing


@dataclass
class Source:
    """One passage given to the model. `n` is the number used for [n] in the answer."""

    n: int
    document_id: str
    filename: str
    page: int
    snippet: str
    score: float
    cited: bool


@dataclass
class ChatResult:
    answer: str
    found: bool
    sources: list[Source]


def answer_question(
    question: str,
    document_ids: list[str] | None,
    *,
    session: Session,
    store: VectorStore,
    llm: LLMClient,
) -> ChatResult:
    """Answer a question from the indexed documents, with numbered citations.

    The LLM is only called when retrieval finds passages that are similar
    enough to the question; otherwise the fixed "not found" answer is returned.
    """
    document_ids = document_ids or None  # an empty list means "all documents"
    if document_ids:
        _check_documents_exist(session, document_ids)

    results = store.search(question, k=settings.retrieval_top_k, document_ids=document_ids)
    filenames = _filenames(session, {r.document_id for r in results})
    # Skip chunks whose document row is gone (a delete that failed halfway),
    # and chunks that aren't similar enough to be worth showing the model.
    relevant = [
        r for r in results if r.document_id in filenames and r.score >= settings.min_similarity
    ]
    logger.info(
        "Retrieved %d chunks, %d relevant (scores: %s)",
        len(results),
        len(relevant),
        [round(r.score, 3) for r in results],
    )
    if not relevant:
        return ChatResult(answer=NOT_FOUND_ANSWER, found=False, sources=[])

    chunks = [
        PromptChunk(n=n, filename=filenames[r.document_id], page=r.page, text=r.text)
        for n, r in enumerate(relevant, start=1)
    ]
    raw_answer = llm.generate(build_prompt(question, chunks), system=SYSTEM_PROMPT)

    if is_not_found_answer(raw_answer):
        return ChatResult(answer=NOT_FOUND_ANSWER, found=False, sources=[])

    citations = check_citations(raw_answer, n_sources=len(chunks))
    sources = [
        _source(chunk, result, cited=chunk.n in citations.cited)
        for chunk, result in zip(chunks, relevant)
    ]
    return ChatResult(answer=citations.text, found=True, sources=sources)


def _check_documents_exist(session: Session, document_ids: list[str]) -> None:
    existing = set(session.scalars(select(Document.id).where(Document.id.in_(document_ids))))
    missing = [d for d in document_ids if d not in existing]
    if missing:
        raise UnknownDocumentError(missing)


def _filenames(session: Session, document_ids: set[str]) -> dict[str, str]:
    """document_id -> filename, in one query."""
    if not document_ids:
        return {}
    rows = session.execute(
        select(Document.id, Document.filename).where(Document.id.in_(document_ids))
    )
    return {doc_id: filename for doc_id, filename in rows}


def _source(chunk: PromptChunk, result: SearchResult, cited: bool) -> Source:
    return Source(
        n=chunk.n,
        document_id=result.document_id,
        filename=chunk.filename,
        page=chunk.page,
        snippet=_snippet(chunk.text),
        score=round(result.score, 3),
        cited=cited,
    )


def _snippet(text: str) -> str:
    """The start of the chunk, cut at a word boundary."""
    if len(text) <= SNIPPET_CHARS:
        return text
    cut = text[:SNIPPET_CHARS].rsplit(" ", 1)[0]
    return cut + "…"
