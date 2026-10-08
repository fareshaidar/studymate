import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_db, get_llm_client, get_vector_store
from app.config import settings
from app.db.database import Base, make_engine
from app.db.models import Document
from app.llm.errors import InvalidLLMOutputError, RateLimitError
from app.main import app
from app.rag.chunker import Chunk
from app.rag.study_prompts import NOTHING_USABLE_MESSAGE
from app.rag.vectorstore import VectorStore
from tests.fakes import FakeLLMClient

TEXTS = [
    "A genetic algorithm evolves a population of solutions using selection and mutation.",
    "Selection keeps the fittest individuals so that good solutions survive.",
]

QUIZ_REPLY = json.dumps(
    {
        "questions": [
            {
                "question": "What does mutation add?",
                "options": ["Variety", "Speed", "Memory", "Nothing"],
                "correct_index": 0,
                "explanation": "Mutation adds variety.",
                "passage": 2,
            }
        ]
    }
)


@pytest.fixture
def env(tmp_path):
    """A temp database and store with one two-page document; returns (client, use_llm)."""
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    store = VectorStore(path=tmp_path / "chroma")
    store.add_chunks("doc1", [Chunk(text=t, page=i + 1, index=i) for i, t in enumerate(TEXTS)])
    with Session() as session:
        session.add(Document(id="doc1", filename="ga.pdf", page_count=2, chunk_count=2))
        session.commit()

    def override_db():
        with Session() as session:
            yield session

    def use_llm(llm):
        app.dependency_overrides[get_llm_client] = lambda: llm
        return llm

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_vector_store] = lambda: store
    use_llm(FakeLLMClient())
    # No `with`: skips the startup hook, which would touch the real database.
    yield TestClient(app), use_llm
    app.dependency_overrides.clear()


def test_summary(env):
    client, use_llm = env
    use_llm(FakeLLMClient(reply="GAs evolve solutions."))

    response = client.post("/study/summary", json={"document_ids": ["doc1"]})

    assert response.status_code == 200
    assert response.json() == {
        "found": True,
        "message": None,
        "summary": "GAs evolve solutions.",
        "truncated": False,
        "llm_calls": 1,
        "pages": [{"document_id": "doc1", "filename": "ga.pdf", "pages": [1, 2]}],
    }


def test_quiz(env):
    client, use_llm = env
    use_llm(FakeLLMClient(reply=QUIZ_REPLY))

    response = client.post("/study/quiz", json={"num_questions": 1})

    assert response.status_code == 200
    body = response.json()
    assert body["found"] is True
    (question,) = body["questions"]
    assert question["options"][question["correct_index"]] == "Variety"
    assert question["source"] == {"document_id": "doc1", "filename": "ga.pdf", "page": 2}


def test_flashcards(env):
    client, use_llm = env
    reply = json.dumps({"cards": [{"front": "Selection?", "back": "Keeps the fittest.", "passage": 2}]})
    use_llm(FakeLLMClient(reply=reply))

    response = client.post("/study/flashcards", json={"num_cards": 1, "topic": "  "})

    assert response.status_code == 200
    assert response.json()["cards"] == [
        {
            "front": "Selection?",
            "back": "Keeps the fittest.",
            "source": {"document_id": "doc1", "filename": "ga.pdf", "page": 2},
        }
    ]


@pytest.mark.parametrize("path", ["/study/summary", "/study/quiz", "/study/flashcards"])
def test_unknown_document_is_404(env, path):
    client, use_llm = env
    llm = use_llm(FakeLLMClient())

    response = client.post(path, json={"document_ids": ["nope"]})

    assert response.status_code == 404
    assert response.json()["code"] == "document_not_found"
    assert "nope" not in response.json()["detail"]
    assert llm.calls == []


def test_invalid_json_twice_is_a_friendly_502(env):
    client, use_llm = env
    llm = use_llm(FakeLLMClient(reply="Here are your questions: 1. What is a GA?"))

    response = client.post("/study/quiz", json={"num_questions": 1})

    assert response.status_code == 502
    assert response.json()["detail"] == InvalidLLMOutputError.user_message
    assert len(llm.calls) == 2


def test_nothing_usable_is_a_friendly_message(env, monkeypatch):
    client, use_llm = env
    llm = use_llm(FakeLLMClient())
    monkeypatch.setattr(settings, "min_similarity", 0.99)

    response = client.post("/study/flashcards", json={"topic": "medieval poetry"})

    assert response.status_code == 200
    assert response.json() == {"found": False, "message": NOTHING_USABLE_MESSAGE, "cards": []}
    assert llm.calls == []


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/study/quiz", {"num_questions": 0}),
        ("/study/quiz", {"num_questions": 11}),
        ("/study/flashcards", {"num_cards": 21}),
        ("/study/summary", {"topic": "x" * 201}),
    ],
)
def test_invalid_requests_are_422(env, path, body):
    client, _ = env
    assert client.post(path, json=body).status_code == 422


def test_rate_limit_is_503(env):
    client, use_llm = env
    use_llm(FakeLLMClient(error=RateLimitError("429", retry_after=5)))

    response = client.post("/study/summary", json={})

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "5"


def test_daily_quota_is_429(env):
    # The study tools share the chat's error handler.
    client, use_llm = env
    use_llm(FakeLLMClient(error=RateLimitError("429 quota", daily_quota=True)))

    response = client.post("/study/quiz", json={"num_questions": 3})

    assert response.status_code == 429
    assert "Retry-After" not in response.headers
    assert "try again tomorrow" in response.json()["detail"]
