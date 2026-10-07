import pytest
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db.database import Base, make_engine
from app.db.models import Document
from app.rag.chunker import Chunk
from app.rag.prompts import NOT_FOUND_ANSWER, SYSTEM_PROMPT
from app.rag.vectorstore import VectorStore
from app.services.chat import UnknownDocumentError, answer_question
from tests.fakes import FakeLLMClient

GA_TEXT = "A genetic algorithm evolves a population of solutions using selection and mutation."
PIZZA_TEXT = "Pepperoni pizza is baked with mozzarella cheese and tomato sauce."


@pytest.fixture
def session(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as session:
        yield session


@pytest.fixture
def store(tmp_path):
    return VectorStore(path=tmp_path / "chroma")


def add_document(session, store, doc_id, filename, texts, first_page=1):
    """Index chunks and record the document, without going through a PDF."""
    chunks = [Chunk(text=t, page=first_page + i, index=i) for i, t in enumerate(texts)]
    store.add_chunks(doc_id, chunks)
    session.add(Document(id=doc_id, filename=filename, page_count=len(texts), chunk_count=len(texts)))
    session.commit()


@pytest.fixture
def threshold(monkeypatch):
    """Set min_similarity explicitly so tests don't depend on exact embedding scores."""

    def set_to(value):
        monkeypatch.setattr(settings, "min_similarity", value)

    return set_to


def ask(question, session, store, llm, document_ids=None):
    return answer_question(question, document_ids, session=session, store=store, llm=llm)


def test_below_threshold_never_calls_the_llm(session, store, threshold):
    add_document(session, store, "doc1", "ga.pdf", [GA_TEXT])
    threshold(0.99)
    llm = FakeLLMClient()

    result = ask("How do genetic algorithms work?", session, store, llm)

    assert llm.calls == []
    assert result.found is False
    assert result.reason == "no_relevant_chunks"
    assert result.answer == NOT_FOUND_ANSWER
    assert result.sources == []


def test_empty_store_returns_not_found(session, store):
    llm = FakeLLMClient()
    result = ask("Anything?", session, store, llm)
    assert result.reason == "no_relevant_chunks"
    assert result.found is False
    assert llm.calls == []


def test_answer_with_sources(session, store, threshold):
    add_document(session, store, "doc1", "ga.pdf", [GA_TEXT], first_page=4)
    threshold(0.0)
    llm = FakeLLMClient(reply="GAs use selection and mutation [1].")

    result = ask("How do genetic algorithms work?", session, store, llm)

    assert result.found is True
    assert result.reason == "ok"
    assert result.answer == "GAs use selection and mutation [1]."
    prompt, system = llm.calls[0]
    assert system == SYSTEM_PROMPT
    assert "[1] (ga.pdf, page 4)" in prompt
    assert GA_TEXT in prompt
    source = result.sources[0]
    assert (source.n, source.filename, source.page, source.document_id) == (1, "ga.pdf", 4, "doc1")
    assert source.snippet == GA_TEXT
    assert source.cited is True
    assert 0 < source.score <= 1


def test_invalid_citations_are_removed(session, store, threshold):
    add_document(session, store, "doc1", "ga.pdf", [GA_TEXT])
    threshold(0.0)
    llm = FakeLLMClient(reply="GAs use mutation [1][7]. Pizza is tasty [9].")

    result = ask("How do genetic algorithms work?", session, store, llm)

    assert result.answer == "GAs use mutation [1]. Pizza is tasty."
    assert [s.cited for s in result.sources] == [True]


def test_uncited_sources_are_flagged(session, store, threshold):
    add_document(session, store, "doc1", "notes.pdf", [GA_TEXT, PIZZA_TEXT])
    threshold(0.0)
    llm = FakeLLMClient(reply="Selection and mutation [1].")

    result = ask("How do genetic algorithms work?", session, store, llm)

    assert [s.n for s in result.sources] == [1, 2]
    assert [s.cited for s in result.sources] == [True, False]


def test_document_ids_limit_the_search(session, store, threshold):
    add_document(session, store, "doc1", "ga.pdf", [GA_TEXT])
    add_document(session, store, "doc2", "pizza.pdf", [PIZZA_TEXT])
    threshold(0.0)
    llm = FakeLLMClient(reply="Answer [1].")

    result = ask("How do genetic algorithms work?", session, store, llm, document_ids=["doc2"])

    prompt, _ = llm.calls[0]
    assert "pizza.pdf" in prompt
    assert "ga.pdf" not in prompt
    assert {s.document_id for s in result.sources} == {"doc2"}


def test_empty_document_ids_means_all_documents(session, store, threshold):
    add_document(session, store, "doc1", "ga.pdf", [GA_TEXT])
    add_document(session, store, "doc2", "pizza.pdf", [PIZZA_TEXT])
    threshold(0.0)

    result = ask("food or algorithms?", session, store, FakeLLMClient(), document_ids=[])

    assert {s.document_id for s in result.sources} == {"doc1", "doc2"}


def test_unknown_document_id_raises(session, store):
    add_document(session, store, "doc1", "ga.pdf", [GA_TEXT])
    with pytest.raises(UnknownDocumentError) as info:
        ask("Anything?", session, store, FakeLLMClient(), document_ids=["doc1", "nope"])
    assert info.value.missing == ["nope"]


def test_chunks_below_threshold_are_dropped(session, store, threshold):
    add_document(session, store, "doc1", "notes.pdf", [GA_TEXT, PIZZA_TEXT])
    scores = {r.text: r.score for r in store.search("How do genetic algorithms work?", k=2)}
    # Put the threshold between the relevant and the unrelated chunk.
    threshold((scores[GA_TEXT] + scores[PIZZA_TEXT]) / 2)
    llm = FakeLLMClient(reply="Answer [1].")

    result = ask("How do genetic algorithms work?", session, store, llm)

    assert [s.snippet for s in result.sources] == [GA_TEXT]
    assert PIZZA_TEXT not in llm.calls[0][0]


def test_orphan_chunks_are_skipped(session, store, threshold):
    add_document(session, store, "doc1", "ga.pdf", [GA_TEXT])
    # Chunks with no database row, as if a delete failed halfway.
    store.add_chunks("ghost", [Chunk(text=GA_TEXT, page=1, index=0)])
    threshold(0.0)
    llm = FakeLLMClient(reply="Answer [1].")

    result = ask("How do genetic algorithms work?", session, store, llm)

    assert {s.document_id for s in result.sources} == {"doc1"}


def test_orphan_chunks_do_not_take_top_k_slots(session, store, threshold, monkeypatch):
    # The bug seen on real data: an orphan copy of the same PDF (no DB row) scored
    # as high as the real chunks, filled top-k, and was then dropped, leaving too few sources.
    texts = [GA_TEXT, "Selection keeps the fittest individuals.", "Mutation adds variety."]
    add_document(session, store, "doc1", "ga.pdf", texts)
    store.add_chunks("ghost", [Chunk(text=t, page=1, index=i) for i, t in enumerate(texts)])
    threshold(0.0)
    monkeypatch.setattr(settings, "retrieval_top_k", 3)

    result = ask("How do genetic algorithms work?", session, store, FakeLLMClient(reply="A [1]."))

    assert len(result.sources) == 3
    assert {s.document_id for s in result.sources} == {"doc1"}


DIAGRAM = "┌──────┐ │ Genetic │ └──┬───┘ ↓ ┌──────┐ │ algorithm │ └──┬───┘ ↓ ┌────┐ │ Stop │ └────┘"


def test_symbol_heavy_chunk_is_dropped_and_replaced(session, store, threshold, monkeypatch):
    texts = [DIAGRAM, GA_TEXT, "Selection keeps the fittest genetic algorithm individuals."]
    add_document(session, store, "doc1", "ga.pdf", texts)
    threshold(0.0)
    monkeypatch.setattr(settings, "retrieval_top_k", 2)
    llm = FakeLLMClient(reply="A [1].")

    result = ask("genetic algorithm", session, store, llm)

    # The diagram is gone, and over-fetching still fills both slots with real text.
    assert len(result.sources) == 2
    assert all("┌" not in s.snippet for s in result.sources)
    assert "┌" not in llm.calls[0][0]


def test_mixed_chunk_is_kept_without_diagram_chars(session, store, threshold):
    mixed = "│ Counter < n_gen ? │ └───┬───┘ ↓ " + GA_TEXT + " It stops after 20 stale generations."
    add_document(session, store, "doc1", "ga.pdf", [mixed])
    threshold(0.0)
    llm = FakeLLMClient(reply="It stops after 20 stale generations [1].")

    result = ask("What stopping condition does the algorithm use?", session, store, llm)

    prompt = llm.calls[0][0]
    assert "It stops after 20 stale generations." in prompt
    assert "Counter < n_gen ?" in prompt
    assert not any(c in prompt for c in "│└┬↓")
    assert not any(c in result.sources[0].snippet for c in "│└┬↓")


def test_reason_is_logged(session, store, threshold, caplog):
    add_document(session, store, "doc1", "ga.pdf", [GA_TEXT])
    threshold(0.0)

    with caplog.at_level("INFO", logger="app.services.chat"):
        ask("How do genetic algorithms work?", session, store, FakeLLMClient(reply="A [1]."))

    assert "chat reason=ok retrieved=1 kept=1" in caplog.text
    # The question itself is not logged.
    assert "genetic" not in caplog.text


@pytest.mark.parametrize(
    "reply",
    ["I couldn't find this in your documents.", "Sorry, I could not find this in your documents"],
)
def test_llm_not_found_reply_means_not_found(session, store, threshold, reply):
    add_document(session, store, "doc1", "ga.pdf", [GA_TEXT])
    threshold(0.0)

    result = ask("What is the capital of France?", session, store, FakeLLMClient(reply=reply))

    assert result.found is False
    assert result.reason == "model_declined"
    assert result.answer == NOT_FOUND_ANSWER
    assert result.sources == []


def test_long_chunks_get_a_short_snippet(session, store, threshold):
    long_text = "Genetic algorithms " + "evolve solutions over many generations " * 20
    add_document(session, store, "doc1", "ga.pdf", [long_text])
    threshold(0.0)

    result = ask("genetic algorithms", session, store, FakeLLMClient(reply="Yes [1]."))

    snippet = result.sources[0].snippet
    assert len(snippet) <= 201
    assert snippet.endswith("…")
    assert not snippet[:-1].endswith(" ")
