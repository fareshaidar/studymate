from dataclasses import asdict

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Conversation, Message
from app.llm.base import LLMClient
from app.rag.prompts import HistoryMessage
from app.rag.text_quality import shorten
from app.rag.vectorstore import VectorStore
from app.services.chat import ChatResult, answer_question

# Conversation titles are the first question, cut to about this length.
TITLE_CHARS = 60


class UnknownConversationError(LookupError):
    """A conversation id was given that doesn't exist."""

    def __init__(self, conversation_id: str):
        super().__init__(f"Conversation not found: {conversation_id}")
        self.conversation_id = conversation_id


def chat_in_conversation(
    question: str,
    document_ids: list[str] | None,
    conversation_id: str | None,
    *,
    session: Session,
    store: VectorStore,
    llm: LLMClient,
) -> tuple[str, ChatResult]:
    """Answer a question inside a conversation and save both messages.

    Without `conversation_id` a new conversation is started. Returns the
    conversation id and the answer. Nothing is saved if answering fails, so a
    failed request never leaves a question without an answer, or an empty conversation.
    """
    if conversation_id is None:
        conversation = Conversation(title=shorten(question, TITLE_CHARS))
        history: list[HistoryMessage] = []
    else:
        conversation = session.get(Conversation, conversation_id)
        if conversation is None:
            raise UnknownConversationError(conversation_id)
        history = recent_history(session, conversation_id, settings.history_window)

    result = answer_question(
        question, document_ids, session=session, store=store, llm=llm, history=history
    )

    # The original question is saved, not the rewrite: the history should show
    # what the student actually typed.
    session.add_all(
        [
            Message(conversation=conversation, role="user", content=question),
            Message(
                conversation=conversation,
                role="assistant",
                content=result.answer,
                sources=[asdict(s) for s in result.sources],
                reason=result.reason,
            ),
        ]
    )
    try:
        session.commit()
    except IntegrityError as exc:
        # With foreign keys on, saving messages fails if the conversation was deleted
        # while the answer was being computed (e.g. from another tab). Nothing is saved
        # (no orphan messages) and the caller answers 404 "conversation no longer exists".
        session.rollback()
        if conversation_id is not None:
            raise UnknownConversationError(conversation_id) from exc
        raise
    return conversation.id, result


def recent_history(session: Session, conversation_id: str, limit: int) -> list[HistoryMessage]:
    """The last `limit` messages of a conversation, oldest first.

    Only these are loaded from the database, so a long conversation doesn't
    make every request slower.
    """
    if limit <= 0:
        return []
    newest_first = session.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.id.desc())
        .limit(limit)
    )
    return [HistoryMessage(m.role, m.content) for m in reversed(list(newest_first))]
