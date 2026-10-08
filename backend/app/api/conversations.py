from datetime import datetime

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.chat import SourceOut
from app.api.deps import get_db
from app.api.errors import conversation_not_found
from app.db.models import Conversation

router = APIRouter(prefix="/conversations", tags=["conversations"])


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    created_at: datetime


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    content: str
    sources: list[SourceOut] | None  # assistant messages only
    reason: str | None  # assistant messages only
    created_at: datetime


class ConversationDetailOut(ConversationOut):
    messages: list[MessageOut]


def _get_or_404(session: Session, conversation_id: str) -> Conversation:
    conversation = session.get(Conversation, conversation_id)
    if conversation is None:
        raise conversation_not_found()
    return conversation


@router.get("", response_model=list[ConversationOut])
def list_conversations(session: Session = Depends(get_db)) -> list[Conversation]:
    """All conversations, newest first (without their messages)."""
    return list(session.scalars(select(Conversation).order_by(Conversation.created_at.desc())))


@router.get("/{conversation_id}", response_model=ConversationDetailOut)
def get_conversation(conversation_id: str, session: Session = Depends(get_db)) -> Conversation:
    """One conversation with all its messages, oldest first, and the sources of each answer."""
    return _get_or_404(session, conversation_id)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(conversation_id: str, session: Session = Depends(get_db)) -> Response:
    """Delete a conversation and its messages (removed by the ORM cascade on Conversation)."""
    session.delete(_get_or_404(session, conversation_id))
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
