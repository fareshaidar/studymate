import pytest
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db.database import Base, make_engine
from app.db.models import Document
from app.rag.chunker import Chunk
from app.rag.study_prompts import NOTHING_USABLE_MESSAGE, SUMMARY_SYSTEM_PROMPT
from app.rag.vectorstore import VectorStore
from app.services.selection import UnknownDocumentError
from app.services.study import summarize
from tests.fakes import FakeLLMClient

GA_TEXT = "A genetic algorithm evolves a population of solutions using selection and mutation."
PIZZA_TEXT = "Pepperoni pizza is baked with mozzarella cheese and tomato sauce."
DIAGRAM = "┌──────┐ │ A │ └──┬───┘ ↓ ┌──────┐ │ B │ └──┬───┘ ↓ ┌────┐ │ C │ └────┘"


@pytest.fixture
def session(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as session:
        yield session


@pytest.fixture
def store(tmp_path):
    return VectorStore(path=tmp_path / "chroma")


def add_document(session, store, doc_id, filename, texts):
    """Index one chunk per page (page 1, 2, ...) and record the document."""
    store.add_chunks(doc_id, [Chunk(text=t, page=i + 1, index=i) for i, t in enumerate(texts)])
    session.add(Document(id=doc_id, filename=filename, page_count=len(texts), chunk_count=len(texts)))
    session.commit()


def page_texts(n):
    """n usable chunk texts of the same length (61 characters each)."""
    return [f"Page {i:02d} explains one step of the genetic algorithm in detail." for i in range(1, n + 1)]


def summarise(session, store, llm, document_ids=None, topic=None):
    return summarize(document_ids, topic, session=session, store=store, llm=llm)


# --- Summaries ---


def test_small_document_uses_a_single_call(session, store):
    add_document(session, store, "doc1", "ga.pdf", [GA_TEXT, PIZZA_TEXT])
    llm = FakeLLMClient(reply="  A short summary.  ")

    result = summarise(session, store, llm)

    assert len(llm.calls) == 1
    prompt, system = llm.calls[0]
    assert system == SUMMARY_SYSTEM_PROMPT
    assert prompt.index(GA_TEXT) < prompt.index(PIZZA_TEXT)  # page order
    assert "part 1 of" not in prompt
    assert result.found is True
    assert result.summary == "A short summary."
    assert result.truncated is False
    assert result.llm_calls == 1
    assert [(p.document_id, p.filename, p.pages) for p in result.pages] == [("doc1", "ga.pdf", [1, 2])]


def test_long_document_is_mapped_then_combined(session, store, monkeypatch):
    add_document(session, store, "doc1", "ga.pdf", page_texts(6))
    monkeypatch.setattr(settings, "study_batch_chars", 130)  # 2 chunks of 61 chars per batch
    llm = FakeLLMClient(replies=["part A", "part B", "part C", "Combined summary."])

    result = summarise(session, store, llm)

    assert len(llm.calls) == 4  # 3 batches + 1 combine
    map_prompts = [prompt for prompt, _ in llm.calls[:3]]
    assert "part 1 of 3" in map_prompts[0] and "Page 01" in map_prompts[0] and "Page 02" in map_prompts[0]
    assert "part 3 of 3" in map_prompts[2] and "Page 06" in map_prompts[2]
    combine_prompt = llm.calls[3][0]
    assert combine_prompt.index("part A") < combine_prompt.index("part B") < combine_prompt.index("part C")
    assert "Page 01" not in combine_prompt  # the combine step only sees the partial summaries
    assert result.summary == "Combined summary."
    assert result.llm_calls == 4
    assert result.truncated is False
    assert result.pages[0].pages == [1, 2, 3, 4, 5, 6]


def test_call_cap_spreads_batches_and_sets_truncated(session, store, monkeypatch):
    add_document(session, store, "doc1", "ga.pdf", page_texts(10))
    monkeypatch.setattr(settings, "study_batch_chars", 130)  # 5 batches: pages 1-2, 3-4, ... 9-10
    monkeypatch.setattr(settings, "study_max_llm_calls", 3)  # room for 2 batches + combine
    llm = FakeLLMClient(replies=["part A", "part B", "Combined."])

    result = summarise(session, store, llm)

    assert len(llm.calls) == 3
    assert result.truncated is True
    assert result.llm_calls == 3
    # Batches 2 and 4 of 5 (evenly spread), so pages 3-4 and 7-8 only.
    assert result.pages[0].pages == [3, 4, 7, 8]
    assert "Page 03" in llm.calls[0][0] and "Page 07" in llm.calls[1][0]


def test_cap_never_exceeded_with_default_settings(session, store, monkeypatch):
    add_document(session, store, "doc1", "ga.pdf", page_texts(40))
    monkeypatch.setattr(settings, "study_batch_chars", 70)  # 1 chunk per batch, 40 batches
    llm = FakeLLMClient(reply="Summary.")

    result = summarise(session, store, llm)

    assert len(llm.calls) == settings.study_max_llm_calls == 8
    assert result.truncated is True


def test_topic_keeps_only_relevant_chunks(session, store, monkeypatch):
    add_document(session, store, "doc1", "notes.pdf", [GA_TEXT, PIZZA_TEXT])
    scores = {r.text: r.score for r in store.search("genetic algorithms", k=2)}
    monkeypatch.setattr(settings, "min_similarity", (scores[GA_TEXT] + scores[PIZZA_TEXT]) / 2)
    llm = FakeLLMClient(reply="GA summary.")

    result = summarise(session, store, llm, topic="genetic algorithms")

    prompt = llm.calls[0][0]
    assert GA_TEXT in prompt
    assert PIZZA_TEXT not in prompt
    assert "Focus on this topic: genetic algorithms" in prompt
    assert result.pages[0].pages == [1]


def test_unrelated_topic_means_no_llm_call(session, store, monkeypatch):
    add_document(session, store, "doc1", "ga.pdf", [GA_TEXT])
    monkeypatch.setattr(settings, "min_similarity", 0.99)
    llm = FakeLLMClient()

    result = summarise(session, store, llm, topic="medieval poetry")

    assert llm.calls == []
    assert result.found is False
    assert result.message == NOTHING_USABLE_MESSAGE


def test_diagram_chunks_never_reach_the_prompt(session, store):
    add_document(session, store, "doc1", "ga.pdf", [DIAGRAM, GA_TEXT])
    llm = FakeLLMClient(reply="Summary.")

    result = summarise(session, store, llm)

    assert "┌" not in llm.calls[0][0]
    assert result.pages[0].pages == [2]


def test_only_diagrams_means_no_llm_call(session, store):
    add_document(session, store, "doc1", "flow.pdf", [DIAGRAM])
    llm = FakeLLMClient()

    result = summarise(session, store, llm)

    assert llm.calls == []
    assert result.found is False


def test_no_documents_means_no_llm_call(session, store):
    llm = FakeLLMClient()
    assert summarise(session, store, llm).found is False
    assert llm.calls == []


def test_unknown_document_raises(session, store):
    add_document(session, store, "doc1", "ga.pdf", [GA_TEXT])
    with pytest.raises(UnknownDocumentError):
        summarise(session, store, FakeLLMClient(), document_ids=["nope"])


def test_selected_documents_only(session, store):
    add_document(session, store, "doc1", "ga.pdf", [GA_TEXT])
    add_document(session, store, "doc2", "pizza.pdf", [PIZZA_TEXT])
    llm = FakeLLMClient(reply="Summary.")

    result = summarise(session, store, llm, document_ids=["doc2"])

    assert PIZZA_TEXT in llm.calls[0][0]
    assert GA_TEXT not in llm.calls[0][0]
    assert [p.document_id for p in result.pages] == ["doc2"]


def test_summary_text_is_not_logged(session, store, caplog):
    add_document(session, store, "doc1", "ga.pdf", [GA_TEXT])
    with caplog.at_level("INFO", logger="app.services.study"):
        summarise(session, store, FakeLLMClient(reply="SECRET SUMMARY"))
    assert "study kind=summary chunks=1 batches=1 llm_calls=1 truncated=False" in caplog.text
    assert "SECRET" not in caplog.text
    assert "genetic" not in caplog.text
