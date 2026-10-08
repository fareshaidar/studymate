import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


def _new_id() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Document(Base):
    """One uploaded file. Its chunks live in ChromaDB, linked by this id."""

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_new_id)
    filename: Mapped[str] = mapped_column(String)
    page_count: Mapped[int] = mapped_column(Integer)
    chunk_count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Conversation(Base):
    """One chat thread. Its title is the first question, shortened."""

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_new_id)
    title: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    # The cascade is done by SQLAlchemy, not SQLite: SQLite ignores foreign keys
    # unless they are switched on, so deleting a conversation in the ORM is what
    # removes its messages.
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.id",
    )


class Message(Base):
    """One turn in a conversation: the student's question or StudyMate's answer."""

    __tablename__ = "messages"

    # An increasing integer, so messages sort in the order they were added even
    # when two of them get the same timestamp.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(
        String, ForeignKey("conversations.id"), index=True
    )
    role: Mapped[str] = mapped_column(String)  # "user" or "assistant"
    content: Mapped[str] = mapped_column(Text)
    # Assistant messages only: the sources shown with the answer, and why it is what it is.
    sources: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")