from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_db
from app.db.database import Base, make_engine
from app.db.models import Conversation, Message
from app.main import app

SOURCE = {
    "n": 1,
    "document_id": "doc1",
    "filename": "ga.pdf",
    "page": 2,
    "snippet": "A genetic algorithm evolves a population.",
    "score": 0.81,
    "cited": True,
}


@pytest.fixture
def Session(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


@pytest.fixture
def client(Session):
    def override_db():
        with Session() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    # No `with`: skips the startup hook, which would touch the real database.
    yield TestClient(app)
    app.dependency_overrides.clear()


def add_conversation(Session, title, day):
    """Save a conversation with one question and one answer; returns its id."""
    with Session() as session:
        conv = Conversation(
            title=title,
            created_at=datetime(2026, 10, day, tzinfo=timezone.utc),
            messages=[
                Message(role="user", content=f"{title}?"),
                Message(role="assistant", content="Answer [1].", sources=[SOURCE], reason="ok"),
            ],
        )
        session.add(conv)
        session.commit()
        return conv.id


def count_messages(Session):
    with Session() as session:
        return session.scalar(select(func.count()).select_from(Message))


def test_list_is_newest_first(client, Session):
    add_conversation(Session, "older", day=1)
    add_conversation(Session, "newer", day=2)

    body = client.get("/conversations").json()

    assert [c["title"] for c in body] == ["newer", "older"]
    assert set(body[0]) == {"id", "title", "created_at"}


def test_get_returns_messages_with_sources(client, Session):
    conv_id = add_conversation(Session, "GAs", day=1)

    body = client.get(f"/conversations/{conv_id}").json()

    assert body["id"] == conv_id
    user, assistant = body["messages"]
    assert (user["role"], user["content"], user["sources"], user["reason"]) == (
        "user",
        "GAs?",
        None,
        None,
    )
    assert assistant["role"] == "assistant"
    assert assistant["sources"] == [SOURCE]
    assert assistant["reason"] == "ok"


def test_delete_removes_the_conversation_and_its_messages(client, Session):
    keep = add_conversation(Session, "keep", day=1)
    drop = add_conversation(Session, "drop", day=2)

    response = client.delete(f"/conversations/{drop}")

    assert response.status_code == 204
    assert client.get(f"/conversations/{drop}").status_code == 404
    assert [c["id"] for c in client.get("/conversations").json()] == [keep]
    assert count_messages(Session) == 2  # only the kept conversation's messages


@pytest.mark.parametrize("method", ["get", "delete"])
def test_unknown_conversation_is_404(client, method):
    response = getattr(client, method)("/conversations/nope")
    assert response.status_code == 404
    assert response.json() == {
        "detail": "This conversation no longer exists.",
        "code": "conversation_not_found",
    }
