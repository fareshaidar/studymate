from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_llm_client, get_vector_store
from app.llm.base import LLMClient
from app.rag.vectorstore import VectorStore
from app.services.chat import UnknownDocumentError, answer_question

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    # Limit the search to these documents; empty or missing means all documents.
    document_ids: list[str] | None = None

    @field_validator("question", mode="before")
    @classmethod
    def strip_question(cls, value):
        return value.strip() if isinstance(value, str) else value


class SourceOut(BaseModel):
    n: int
    document_id: str
    filename: str
    page: int
    snippet: str
    score: float
    cited: bool


class ChatResponse(BaseModel):
    answer: str
    found: bool
    sources: list[SourceOut]


@router.post("", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    session: Session = Depends(get_db),
    store: VectorStore = Depends(get_vector_store),
    llm: LLMClient = Depends(get_llm_client),
) -> dict:
    """Answer a question from the uploaded documents. Plain `def`: embedding and the LLM call block.

    LLM failures are turned into friendly 5xx responses by the handlers in app/api/errors.py.
    """
    try:
        result = answer_question(
            request.question, request.document_ids, session=session, store=store, llm=llm
        )
    except UnknownDocumentError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return asdict(result)
