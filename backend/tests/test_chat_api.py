import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_db, get_llm_client, get_vector_store
from app.config import settings
from app.db.database import Base, make_engine
from app.db.models import Conversation, Document, Message
from app.llm.errors import MissingAPIKeyError, ProviderError, RateLimitError
from app.main import app
from app.rag.chunker import Chunk
from app.rag.vectorstore import VectorStore
from tests.fakes import FakeLLMClient

GA_TEXT = "A genetic algorithm evolves a population of solutions using selection and mutation."


@pytest.fixture
def Session(tmp_path):
    """Session factory for the temp database the app uses in these tests."""
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


@pytest.fixture
def env(tmp_path, monkeypatch, Session):
    """A temp database and vector store with one indexed document; returns (client, use_llm)."""
    store = VectorStore(path=tmp_path / "chroma")
    store.add_chunks("doc1", [Chunk(text=GA_TEXT, page=2, index=0)])
    with Session() as session:
        session.add(Document(id="doc1", filename="ga.pdf", page_count=3, chunk_count=1))
        session.commit()
    monkeypatch.setattr(settings, "min_similarity", 0.0)

    def override_db():
        with Session() as session:
            yield session

    def use_llm(llm):
        app.dependency_overrides[get_llm_client] = lambda: llm
        return llm

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_vector_store] = lambda: store
    use_llm(FakeLLMClient(reply="GAs use selection and mutation [1]."))
    # No `with`: skips the startup hook, which would touch the real database.
    yield TestClient(app), use_llm
    app.dependency_overrides.clear()


def test_chat_returns_answer_and_sources(env):
    client, _ = env
    response = client.post("/chat", json={"question": "How do genetic algorithms work?"})

    assert response.status_code == 200
    body = response.json()
    assert body["found"] is True
    assert body["reason"] == "ok"
    assert body["answer"] == "GAs use selection and mutation [1]."
    assert body["sources"] == [
        {
            "n": 1,
            "document_id": "doc1",
            "filename": "ga.pdf",
            "page": 2,
            "snippet": GA_TEXT,
            "score": body["sources"][0]["score"],
            "cited": True,
        }
    ]


def test_not_found_answer(env, monkeypatch):
    client, use_llm = env
    llm = use_llm(FakeLLMClient())
    monkeypatch.setattr(settings, "min_similarity", 0.99)

    body = client.post("/chat", json={"question": "Best pizza in Naples?"}).json()

    assert body == {
        "answer": "I couldn't find this in your documents.",
        "found": False,
        "reason": "no_relevant_chunks",
        "sources": [],
        "conversation_id": body["conversation_id"],
        "rewritten_question": None,
    }
    assert llm.calls == []


@pytest.mark.parametrize("question", ["", "   ", "x" * 2001])
def test_invalid_question_is_rejected(env, question):
    client, _ = env
    assert client.post("/chat", json={"question": question}).status_code == 422


def test_unknown_document_id_is_404(env):
    client, _ = env
    response = client.post("/chat", json={"question": "Hi?", "document_ids": ["nope"]})
    assert response.status_code == 404
    assert "nope" in response.json()["detail"]


def test_rate_limit_is_503_with_retry_after(env):
    client, use_llm = env
    use_llm(FakeLLMClient(error=RateLimitError("429 from Gemini", retry_after=12.3)))

    response = client.post("/chat", json={"question": "How do GAs work?"})

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "13"
    assert response.json()["detail"] == RateLimitError.user_message


def test_provider_error_is_502(env):
    client, use_llm = env
    use_llm(FakeLLMClient(error=ProviderError("Gemini error 500 INTERNAL: boom", status_code=500)))

    response = client.post("/chat", json={"question": "How do GAs work?"})

    assert response.status_code == 502
    # The technical detail stays in the logs, never in the response.
    assert "boom" not in response.text
    assert response.json()["detail"] == ProviderError.user_message


def test_missing_key_is_500(env):
    client, _ = env

    def no_key():
        raise MissingAPIKeyError("GEMINI_API_KEY is not set.")

    app.dependency_overrides[get_llm_client] = no_key
    response = client.post("/chat", json={"question": "How do GAs work?"})

    assert response.status_code == 500
    assert response.json()["detail"] == MissingAPIKeyError.user_message


# --- Conversations ---


def count(Session, model):
    with Session() as session:
        return session.scalar(select(func.count()).select_from(model))


def test_first_question_starts_a_conversation_with_a_short_title(env, Session):
    client, _ = env
    question = "How do genetic algorithms " + "really " * 20 + "work?"

    body = client.post("/chat", json={"question": question}).json()

    with Session() as session:
        conv = session.get(Conversation, body["conversation_id"])
        assert conv.title.startswith("How do genetic algorithms")
        assert conv.title.endswith("…")
        assert len(conv.title) <= 61
        assert [(m.role, m.content) for m in conv.messages] == [
            ("user", question),
            ("assistant", "GAs use selection and mutation [1]."),
        ]
        assert conv.messages[1].reason == "ok"
        assert conv.messages[1].sources[0]["filename"] == "ga.pdf"
    assert body["rewritten_question"] is None


def test_full_passage_text_is_neither_returned_nor_stored(env, Session):
    client, _ = env

    body = client.post("/chat", json={"question": "How do GAs work?"}).json()

    assert "passages" not in body
    source_fields = {"n", "document_id", "filename", "page", "snippet", "score", "cited"}
    assert set(body["sources"][0]) == source_fields
    with Session() as session:
        stored = session.get(Conversation, body["conversation_id"]).messages[1]
        assert set(stored.sources[0]) == source_fields


def test_follow_up_continues_the_conversation(env, Session):
    client, use_llm = env
    first = client.post("/chat", json={"question": "How do GAs work?"}).json()
    llm = use_llm(FakeLLMClient(replies=["What does mutation do in a GA?", "It adds variety [1]."]))

    body = client.post(
        "/chat",
        json={"question": "And mutation?", "conversation_id": first["conversation_id"]},
    ).json()

    assert body["conversation_id"] == first["conversation_id"]
    assert body["rewritten_question"] == "What does mutation do in a GA?"
    assert "Student: How do GAs work?" in llm.calls[0][0]
    assert count(Session, Conversation) == 1
    assert count(Session, Message) == 4


def test_unknown_conversation_id_is_404(env, Session):
    client, use_llm = env
    llm = use_llm(FakeLLMClient())

    response = client.post("/chat", json={"question": "Hi?", "conversation_id": "nope"})

    assert response.status_code == 404
    assert "nope" in response.json()["detail"]
    assert llm.calls == []
    assert count(Session, Message) == 0


def test_history_window_is_respected(env, Session, monkeypatch):
    client, use_llm = env
    with Session() as session:
        conv = Conversation(
            title="old",
            messages=[
                Message(role="user" if i % 2 == 0 else "assistant", content=f"message-{i}")
                for i in range(8)
            ],
        )
        session.add(conv)
        session.commit()
        conv_id = conv.id
    monkeypatch.setattr(settings, "history_window", 2)
    llm = use_llm(FakeLLMClient(replies=["How do GAs work?", "Answer [1]."]))

    client.post("/chat", json={"question": "And then?", "conversation_id": conv_id})

    rewrite_prompt, answer_prompt = llm.calls[0][0], llm.calls[1][0]
    for prompt in (rewrite_prompt, answer_prompt):
        assert "message-6" in prompt
        assert "message-7" in prompt
        assert "message-5" not in prompt
    assert rewrite_prompt.index("message-6") < rewrite_prompt.index("message-7")


def test_failed_answer_saves_nothing(env, Session):
    client, use_llm = env
    use_llm(FakeLLMClient(error=ProviderError("boom", status_code=500)))

    response = client.post("/chat", json={"question": "How do GAs work?"})

    assert response.status_code == 502
    assert count(Session, Conversation) == 0
    assert count(Session, Message) == 0
