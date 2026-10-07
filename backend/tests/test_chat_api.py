import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_db, get_llm_client, get_vector_store
from app.config import settings
from app.db.database import Base, make_engine
from app.db.models import Document
from app.llm.errors import MissingAPIKeyError, ProviderError, RateLimitError
from app.main import app
from app.rag.chunker import Chunk
from app.rag.vectorstore import VectorStore
from tests.fakes import FakeLLMClient

GA_TEXT = "A genetic algorithm evolves a population of solutions using selection and mutation."


@pytest.fixture
def env(tmp_path, monkeypatch):
    """A temp database and vector store with one indexed document; returns (client, use_llm)."""
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
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

    assert body == {"answer": "I couldn't find this in your documents.", "found": False, "sources": []}
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
