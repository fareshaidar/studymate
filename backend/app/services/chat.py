import logging
from dataclasses import dataclass
from typing import Literal

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
from app.rag.text_quality import alnum_ratio, shorten, strip_diagram_chars
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


# Why the answer is what it is: answered, nothing relevant retrieved, or the model said "not found".
Reason = Literal["ok", "no_relevant_chunks", "model_declined"]


@dataclass
class ChatResult:
    answer: str
    found: bool
    reason: Reason
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
    filenames = _filenames(session, document_ids)
    if document_ids:
        missing = [d for d in document_ids if d not in filenames]
        if missing:
            raise UnknownDocumentError(missing)
    if not filenames:
        return _finish("no_relevant_chunks", results=[], kept=[])

    # Always search only documents that exist in the database, so chunks left
    # behind without a row (orphans) can't take any of the top-k slots.
    # Over-fetch, so chunks dropped below are replaced by the next best ones.
    results = store.search(
        question, k=settings.retrieval_top_k * 2, document_ids=list(filenames)
    )
    relevant = [
        r
        for r in results
        if r.score >= settings.min_similarity and alnum_ratio(r.text) >= settings.min_alnum_ratio
    ][: settings.retrieval_top_k]
    if not relevant:
        return _finish("no_relevant_chunks", results=results, kept=relevant)

    # Diagram characters in mixed chunks are noise for the model and the snippet.
    chunks = [
        PromptChunk(
            n=n, filename=filenames[r.document_id], page=r.page, text=strip_diagram_chars(r.text)
        )
        for n, r in enumerate(relevant, start=1)
    ]
    raw_answer = llm.generate(build_prompt(question, chunks), system=SYSTEM_PROMPT)

    if is_not_found_answer(raw_answer):
        return _finish("model_declined", results=results, kept=relevant)

    citations = check_citations(raw_answer, n_sources=len(chunks))
    sources = [
        _source(chunk, result, cited=chunk.n in citations.cited)
        for chunk, result in zip(chunks, relevant)
    ]
    return _finish("ok", results=results, kept=relevant, answer=citations.text, sources=sources)


def _finish(
    reason: Reason,
    *,
    results: list[SearchResult],
    kept: list[SearchResult],
    answer: str = NOT_FOUND_ANSWER,
    sources: list[Source] | None = None,
) -> ChatResult:
    """Log the outcome once per request (no question or answer text) and build the result."""
    logger.info(
        "chat reason=%s retrieved=%d kept=%d scores=%s",
        reason,
        len(results),
        len(kept),
        [round(r.score, 3) for r in results],
    )
    return ChatResult(answer=answer, found=reason == "ok", reason=reason, sources=sources or [])


def _filenames(session: Session, document_ids: list[str] | None) -> dict[str, str]:
    """document_id -> filename for the given documents (or all of them), in one query."""
    query = select(Document.id, Document.filename)
    if document_ids is not None:
        query = query.where(Document.id.in_(document_ids))
    return {doc_id: filename for doc_id, filename in session.execute(query)}


def _source(chunk: PromptChunk, result: SearchResult, cited: bool) -> Source:
    return Source(
        n=chunk.n,
        document_id=result.document_id,
        filename=chunk.filename,
        page=chunk.page,
        snippet=shorten(chunk.text, SNIPPET_CHARS),
        score=round(result.score, 3),
        cited=cited,
    )
