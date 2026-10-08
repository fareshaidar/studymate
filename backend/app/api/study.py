from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_llm_client, get_vector_store
from app.llm.base import LLMClient
from app.rag.vectorstore import VectorStore
from app.services.selection import UnknownDocumentError
from app.services.study import make_flashcards, make_quiz, summarize

router = APIRouter(prefix="/study", tags=["study"])


class StudyRequest(BaseModel):
    # Which documents to use; empty or missing means all documents.
    document_ids: list[str] = []
    topic: str | None = Field(default=None, max_length=200)

    @field_validator("topic", mode="before")
    @classmethod
    def blank_topic_means_none(cls, value):
        # "  " is treated as no topic rather than as a topic made of spaces.
        if isinstance(value, str):
            return value.strip() or None
        return value


class QuizRequest(StudyRequest):
    num_questions: int = Field(default=5, ge=1, le=10)


class FlashcardsRequest(StudyRequest):
    num_cards: int = Field(default=10, ge=1, le=20)


class DocumentPagesOut(BaseModel):
    document_id: str
    filename: str
    pages: list[int]


class SummaryResponse(BaseModel):
    found: bool
    message: str | None  # why there is no summary, when found is false
    summary: str
    truncated: bool  # true if part of the material was skipped to stay within the call budget
    llm_calls: int
    pages: list[DocumentPagesOut]


class ItemSourceOut(BaseModel):
    document_id: str
    filename: str
    page: int


class QuizQuestionOut(BaseModel):
    question: str
    options: list[str]
    correct_index: int
    explanation: str
    source: ItemSourceOut


class QuizResponse(BaseModel):
    found: bool
    message: str | None
    questions: list[QuizQuestionOut]


class FlashcardOut(BaseModel):
    front: str
    back: str
    source: ItemSourceOut


class FlashcardsResponse(BaseModel):
    found: bool
    message: str | None
    cards: list[FlashcardOut]


def _not_found(exc: UnknownDocumentError) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


@router.post("/summary", response_model=SummaryResponse)
def summary(
    request: StudyRequest,
    session: Session = Depends(get_db),
    store: VectorStore = Depends(get_vector_store),
    llm: LLMClient = Depends(get_llm_client),
) -> dict:
    """Summarise documents (optionally on one topic). Plain `def`: the LLM calls block."""
    try:
        result = summarize(
            request.document_ids, request.topic, session=session, store=store, llm=llm
        )
    except UnknownDocumentError as exc:
        raise _not_found(exc) from exc
    return asdict(result)


@router.post("/quiz", response_model=QuizResponse)
def quiz(
    request: QuizRequest,
    session: Session = Depends(get_db),
    store: VectorStore = Depends(get_vector_store),
    llm: LLMClient = Depends(get_llm_client),
) -> dict:
    """Multiple-choice questions, each with the document and page it comes from."""
    try:
        result = make_quiz(
            request.document_ids,
            request.num_questions,
            request.topic,
            session=session,
            store=store,
            llm=llm,
        )
    except UnknownDocumentError as exc:
        raise _not_found(exc) from exc
    return asdict(result)


@router.post("/flashcards", response_model=FlashcardsResponse)
def flashcards(
    request: FlashcardsRequest,
    session: Session = Depends(get_db),
    store: VectorStore = Depends(get_vector_store),
    llm: LLMClient = Depends(get_llm_client),
) -> dict:
    """Flashcards, each with the document and page it comes from."""
    try:
        result = make_flashcards(
            request.document_ids,
            request.num_cards,
            request.topic,
            session=session,
            store=store,
            llm=llm,
        )
    except UnknownDocumentError as exc:
        raise _not_found(exc) from exc
    return asdict(result)
