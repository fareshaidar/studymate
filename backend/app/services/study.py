"""Study tools built on the indexed documents: summaries, quizzes and flashcards.

Nothing is stored: every request reads the chunks, calls the LLM and returns the result.
"""

import logging
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.config import settings
from app.llm.base import LLMClient
from app.rag.prompts import PromptChunk
from app.rag.study_prompts import (
    NOTHING_USABLE_MESSAGE,
    SUMMARY_SYSTEM_PROMPT,
    build_combine_prompt,
    build_summary_prompt,
)
from app.rag.vectorstore import StoredChunk, VectorStore
from app.services.selection import evenly_spaced, resolve_documents, usable

logger = logging.getLogger(__name__)


@dataclass
class DocumentPages:
    """The pages of one document that a summary was built from."""

    document_id: str
    filename: str
    pages: list[int]


@dataclass
class SummaryResult:
    found: bool
    message: str | None = None  # set when found is False
    summary: str = ""
    truncated: bool = False  # True if some of the material had to be left out (call cap)
    llm_calls: int = 0
    pages: list[DocumentPages] = field(default_factory=list)


def summarize(
    document_ids: list[str] | None,
    topic: str | None,
    *,
    session: Session,
    store: VectorStore,
    llm: LLMClient,
) -> SummaryResult:
    """Summarise documents with map-reduce, within a fixed budget of LLM calls.

    Map: each batch of chunks (in page order) is summarised on its own.
    Reduce: the partial summaries are combined in one more call.
    Material that fits in one batch needs a single call.
    """
    filenames = resolve_documents(session, document_ids)  # raises UnknownDocumentError
    chunks = _summary_chunks(filenames, topic, store)
    if not chunks:
        logger.info("study kind=summary chunks=0 llm_calls=0")
        return SummaryResult(found=False, message=NOTHING_USABLE_MESSAGE)

    batches = _batches(chunks, settings.study_batch_chars)
    # One call per batch plus one to combine them, so at most (cap - 1) batches.
    max_batches = max(settings.study_max_llm_calls - 1, 1)
    truncated = len(batches) > max_batches
    if truncated:
        # Keep a sample spread over the whole material, not just its beginning.
        batches = evenly_spaced(batches, max_batches)

    if len(batches) == 1:
        summary = llm.generate(
            build_summary_prompt(_numbered(batches[0], filenames), topic),
            system=SUMMARY_SYSTEM_PROMPT,
        )
        llm_calls = 1
    else:
        partials = [
            llm.generate(
                build_summary_prompt(_numbered(batch, filenames), topic, part=(i, len(batches))),
                system=SUMMARY_SYSTEM_PROMPT,
            )
            for i, batch in enumerate(batches, start=1)
        ]
        summary = llm.generate(build_combine_prompt(partials, topic), system=SUMMARY_SYSTEM_PROMPT)
        llm_calls = len(batches) + 1

    logger.info(
        "study kind=summary chunks=%d batches=%d llm_calls=%d truncated=%s",
        len(chunks),
        len(batches),
        llm_calls,
        truncated,
    )
    return SummaryResult(
        found=True,
        summary=summary.strip(),
        truncated=truncated,
        llm_calls=llm_calls,
        pages=_pages_covered(batches, filenames),
    )


def _summary_chunks(
    filenames: dict[str, str], topic: str | None, store: VectorStore
) -> list[StoredChunk]:
    """Usable chunks of the documents, each document in page order.

    With a topic, only chunks similar enough to it are kept, so the summary
    stays on topic and fewer LLM calls are needed.
    """
    all_chunks = [c for doc_id in filenames for c in store.get_chunks(doc_id)]
    if topic and all_chunks:
        results = store.search(topic, k=len(all_chunks), document_ids=list(filenames))
        relevant = {
            (r.document_id, r.chunk_index) for r in results if r.score >= settings.min_similarity
        }
        all_chunks = [c for c in all_chunks if (c.document_id, c.chunk_index) in relevant]
    return usable(all_chunks)


def _batches(chunks: list[StoredChunk], max_chars: int) -> list[list[StoredChunk]]:
    """Group consecutive chunks into batches of at most `max_chars` characters.

    A single chunk longer than the budget gets a batch of its own rather than being cut.
    """
    batches: list[list[StoredChunk]] = []
    current: list[StoredChunk] = []
    size = 0
    for chunk in chunks:
        if current and size + len(chunk.text) > max_chars:
            batches.append(current)
            current, size = [], 0
        current.append(chunk)
        size += len(chunk.text)
    if current:
        batches.append(current)
    return batches


def _numbered(chunks: list[StoredChunk], filenames: dict[str, str]) -> list[PromptChunk]:
    return [
        PromptChunk(n=n, filename=filenames[c.document_id], page=c.page, text=c.text)
        for n, c in enumerate(chunks, start=1)
    ]


def _pages_covered(
    batches: list[list[StoredChunk]], filenames: dict[str, str]
) -> list[DocumentPages]:
    """Per document (in the order of `filenames`), the sorted pages that were summarised."""
    pages: dict[str, set[int]] = {}
    for batch in batches:
        for chunk in batch:
            pages.setdefault(chunk.document_id, set()).add(chunk.page)
    return [
        DocumentPages(document_id=doc_id, filename=filename, pages=sorted(pages[doc_id]))
        for doc_id, filename in filenames.items()
        if doc_id in pages
    ]
