import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session

from app.config import settings
from app.llm.base import LLMClient
from app.llm.errors import LLMError
from app.rag.citations import check_citations
from app.rag.prompts import (
    NOT_FOUND_ANSWER,
    REWRITE_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    HistoryMessage,
    PromptChunk,
    build_prompt,
    build_rewrite_prompt,
    is_not_found_answer,
)
from app.rag.text_quality import shorten, strip_diagram_chars
from app.rag.vectorstore import SearchResult, VectorStore
from app.services.selection import (  # noqa: F401  (UnknownDocumentError is re-exported for callers)
    UnknownDocumentError,
    is_usable,
    resolve_documents,
)

logger = logging.getLogger(__name__)

SNIPPET_CHARS = 200
# A standalone question longer than this is more likely an answer or an essay
# than a question, so it isn't trusted for retrieval.
MAX_REWRITE_CHARS = 500


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
    # The standalone question used for retrieval, or None if the original question was used.
    rewritten_question: str | None = None


def rewrite_question(
    question: str, history: Sequence[HistoryMessage], llm: LLMClient
) -> str | None:
    """Turn a follow-up into a standalone question, or None to use the original as it is.

    Never raises for LLM problems: a failed or unusable rewrite only makes
    retrieval a bit worse, so it shouldn't fail the whole request.
    """
    if not history:
        return None  # a first question has nothing to refer back to
    try:
        reply = llm.generate(build_rewrite_prompt(question, history), system=REWRITE_SYSTEM_PROMPT)
    except LLMError as exc:
        # Only the error class: the message is technical detail, and never question text.
        logger.warning("rewrite failed error=%s, using the original question", type(exc).__name__)
        return None

    rewritten = reply.strip()
    problem = _rewrite_problem(rewritten)
    if problem:
        logger.warning("rewrite rejected reason=%s, using the original question", problem)
        return None
    return rewritten


def _rewrite_problem(rewritten: str) -> str | None:
    """Why a rewrite can't be used as a search query, or None if it looks fine."""
    if not rewritten:
        return "empty"
    if len(rewritten) > MAX_REWRITE_CHARS:
        return "too_long"
    if "\n" in rewritten:
        # We asked for one line; several lines usually means the model answered or explained.
        return "multiline"
    return None


def answer_question(
    question: str,
    document_ids: list[str] | None,
    *,
    session: Session,
    store: VectorStore,
    llm: LLMClient,
    history: Sequence[HistoryMessage] = (),
) -> ChatResult:
    """Answer a question from the indexed documents, with numbered citations.

    With `history` (the recent messages of the conversation), a follow-up is first
    rewritten into a standalone question, which is then used for retrieval and in
    the answer prompt. The answer LLM call is only made when retrieval finds passages
    that are similar enough; otherwise the fixed "not found" answer is returned.
    """
    filenames = resolve_documents(session, document_ids)  # raises UnknownDocumentError
    if not filenames:
        # Nothing to search, so don't spend an LLM call on rewriting either.
        return _finish("no_relevant_chunks", results=[], kept=[], history=history)

    rewritten = rewrite_question(question, history, llm)
    standalone = rewritten or question

    # Always search only documents that exist in the database, so chunks left
    # behind without a row (orphans) can't take any of the top-k slots.
    # Over-fetch, so chunks dropped below are replaced by the next best ones.
    results = store.search(
        standalone, k=settings.retrieval_top_k * 2, document_ids=list(filenames)
    )
    relevant = [
        r
        for r in results
        if r.score >= settings.min_similarity and is_usable(r.text)
    ][: settings.retrieval_top_k]
    if not relevant:
        return _finish(
            "no_relevant_chunks", results=results, kept=relevant, history=history, rewritten=rewritten
        )

    # Diagram characters in mixed chunks are noise for the model and the snippet.
    chunks = [
        PromptChunk(
            n=n, filename=filenames[r.document_id], page=r.page, text=strip_diagram_chars(r.text)
        )
        for n, r in enumerate(relevant, start=1)
    ]
    raw_answer = llm.generate(build_prompt(standalone, chunks, history), system=SYSTEM_PROMPT)

    if is_not_found_answer(raw_answer):
        return _finish(
            "model_declined", results=results, kept=relevant, history=history, rewritten=rewritten
        )

    citations = check_citations(raw_answer, n_sources=len(chunks))
    sources = [
        _source(chunk, result, cited=chunk.n in citations.cited)
        for chunk, result in zip(chunks, relevant)
    ]
    return _finish(
        "ok",
        results=results,
        kept=relevant,
        history=history,
        rewritten=rewritten,
        answer=citations.text,
        sources=sources,
    )


def _finish(
    reason: Reason,
    *,
    results: list[SearchResult],
    kept: list[SearchResult],
    history: Sequence[HistoryMessage],
    rewritten: str | None = None,
    answer: str = NOT_FOUND_ANSWER,
    sources: list[Source] | None = None,
) -> ChatResult:
    """Log the outcome once per request (no question or answer text) and build the result."""
    logger.info(
        "chat reason=%s retrieved=%d kept=%d scores=%s history=%d rewritten=%s",
        reason,
        len(results),
        len(kept),
        [round(r.score, 3) for r in results],
        len(history),
        rewritten is not None,
    )
    return ChatResult(
        answer=answer,
        found=reason == "ok",
        reason=reason,
        sources=sources or [],
        rewritten_question=rewritten,
    )


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
