"""Study tools built on the indexed documents: summaries, quizzes and flashcards.

Nothing is stored: every request reads the chunks, calls the LLM and returns the result.
"""

import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.config import settings
from app.llm.base import LLMClient
from app.rag.prompts import PromptChunk
from app.rag.structured import FlashcardsLLM, QuizLLM, generate_json
from app.rag.study_prompts import (
    FLASHCARDS_SYSTEM_PROMPT,
    NOTHING_USABLE_MESSAGE,
    QUIZ_SYSTEM_PROMPT,
    SUMMARY_SYSTEM_PROMPT,
    build_combine_prompt,
    build_flashcards_prompt,
    build_quiz_prompt,
    build_summary_prompt,
)
from app.rag.vectorstore import SearchResult, StoredChunk, VectorStore
from app.services.selection import evenly_spaced, resolve_documents, select_passages, usable

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


@dataclass
class ItemSource:
    """Where a quiz question or flashcard comes from: always one of the passages we sent."""

    document_id: str
    filename: str
    page: int


@dataclass
class QuizQuestion:
    question: str
    options: list[str]
    correct_index: int
    explanation: str
    source: ItemSource


@dataclass
class QuizResult:
    found: bool
    message: str | None = None
    questions: list[QuizQuestion] = field(default_factory=list)


@dataclass
class Flashcard:
    front: str
    back: str
    source: ItemSource


@dataclass
class FlashcardsResult:
    found: bool
    message: str | None = None
    cards: list[Flashcard] = field(default_factory=list)


def summarize(
    document_ids: list[str] | None,
    topic: str | None,
    *,
    session: Session,
    store: VectorStore,
    llm: LLMClient,
    clock: Callable[[], float] = time.monotonic,
) -> SummaryResult:
    """Summarise documents with map-reduce, within a budget of LLM calls and of time.

    Map: each batch of chunks (in page order) is summarised on its own.
    Reduce: the partial summaries are combined in one more call.
    Material that fits in one batch needs a single call.

    Time budget (study_max_seconds): once it is used up, no further batch call is
    started; the batches done so far are combined and the result is marked truncated.
    A call already running is never cut off, so the overrun is at most one batch call
    plus the combine. `clock` is a parameter so tests can make time pass instantly.
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
        done = batches
    else:
        start = clock()
        partials = []
        for i, batch in enumerate(batches, start=1):
            # The first batch always runs, so there is something to show.
            if partials and clock() - start > settings.study_max_seconds:
                logger.info(
                    "study kind=summary stopped after %d of %d batches: time budget",
                    len(partials),
                    len(batches),
                )
                truncated = True
                break
            partials.append(
                llm.generate(
                    build_summary_prompt(_numbered(batch, filenames), topic, part=(i, len(batches))),
                    system=SUMMARY_SYSTEM_PROMPT,
                )
            )
        done = batches[: len(partials)]
        if len(partials) == 1:
            summary, llm_calls = partials[0], 1  # nothing to combine
        else:
            summary = llm.generate(build_combine_prompt(partials, topic), system=SUMMARY_SYSTEM_PROMPT)
            llm_calls = len(partials) + 1

    logger.info(
        "study kind=summary chunks=%d batches=%d llm_calls=%d truncated=%s",
        len(chunks),
        len(done),
        llm_calls,
        truncated,
    )
    return SummaryResult(
        found=True,
        summary=summary.strip(),
        truncated=truncated,
        llm_calls=llm_calls,
        # Only the batches actually summarised: the "Based on" pages must be true.
        pages=_pages_covered(done, filenames),
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


def _numbered(
    chunks: list[StoredChunk] | list[StoredChunk | SearchResult], filenames: dict[str, str]
) -> list[PromptChunk]:
    """The chunks as passages numbered from 1, the numbers the model refers to."""
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


def make_quiz(
    document_ids: list[str] | None,
    num_questions: int,
    topic: str | None,
    *,
    session: Session,
    store: VectorStore,
    llm: LLMClient,
    rng: random.Random | None = None,
) -> QuizResult:
    """Multiple-choice questions from the documents, each linked to the passage it came from.

    The options are shuffled here, not trusted from the model: models tend to put
    the correct answer first. `rng` lets tests make the shuffle repeatable.
    """
    filenames = resolve_documents(session, document_ids)  # raises UnknownDocumentError
    passages = select_passages(list(filenames), topic, settings.study_max_passages, store)
    if not passages:
        logger.info("study kind=quiz passages=0 llm_calls=0")
        return QuizResult(found=False, message=NOTHING_USABLE_MESSAGE)

    chunks = _numbered(passages, filenames)
    quiz = generate_json(
        llm,
        build_quiz_prompt(chunks, num_questions, topic),
        system=QUIZ_SYSTEM_PROMPT,
        schema=QuizLLM,
        context={"n_passages": len(chunks)},
    )
    rng = rng or random.Random()
    questions = []
    # The model may write more items than asked for; extras are dropped.
    for item in quiz.questions[:num_questions]:
        options, correct_index = _shuffled(item.options, item.correct_index, rng)
        questions.append(
            QuizQuestion(
                question=item.question,
                options=options,
                correct_index=correct_index,
                explanation=item.explanation,
                source=_source_of(item.passage, passages, filenames),
            )
        )
    logger.info("study kind=quiz passages=%d items=%d", len(passages), len(questions))
    return QuizResult(found=True, questions=questions)


def make_flashcards(
    document_ids: list[str] | None,
    num_cards: int,
    topic: str | None,
    *,
    session: Session,
    store: VectorStore,
    llm: LLMClient,
) -> FlashcardsResult:
    """Flashcards from the documents, each linked to the passage it came from."""
    filenames = resolve_documents(session, document_ids)  # raises UnknownDocumentError
    passages = select_passages(list(filenames), topic, settings.study_max_passages, store)
    if not passages:
        logger.info("study kind=flashcards passages=0 llm_calls=0")
        return FlashcardsResult(found=False, message=NOTHING_USABLE_MESSAGE)

    chunks = _numbered(passages, filenames)
    result = generate_json(
        llm,
        build_flashcards_prompt(chunks, num_cards, topic),
        system=FLASHCARDS_SYSTEM_PROMPT,
        schema=FlashcardsLLM,
        context={"n_passages": len(chunks)},
    )
    cards = [
        Flashcard(
            front=card.front,
            back=card.back,
            source=_source_of(card.passage, passages, filenames),
        )
        for card in result.cards[:num_cards]
    ]
    logger.info("study kind=flashcards passages=%d items=%d", len(passages), len(cards))
    return FlashcardsResult(found=True, cards=cards)


def _shuffled(options: list[str], correct_index: int, rng: random.Random) -> tuple[list[str], int]:
    """The options in a random order, and the new position of the correct one."""
    order = list(range(len(options)))
    rng.shuffle(order)
    # order[new_position] = old_position, so the correct answer moves to where its old index is.
    return [options[i] for i in order], order.index(correct_index)


def _source_of(
    passage: int,
    passages: list[StoredChunk | SearchResult],
    filenames: dict[str, str],
) -> ItemSource:
    """Document and page of passage number `passage` (1-based), from what we sent.

    The model only gives the passage number (already checked to be in range),
    never a page, so a wrong page can't be invented.
    """
    chunk = passages[passage - 1]
    return ItemSource(
        document_id=chunk.document_id, filename=filenames[chunk.document_id], page=chunk.page
    )
