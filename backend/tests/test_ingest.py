import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.db.database import Base, make_engine
from app.db.models import Document
from app.rag.vectorstore import VectorStore
from app.services.ingest import IngestError, ingest_pdf
from tests.helpers import make_pdf

GA_TEXT = "A genetic algorithm evolves a population of solutions using mutation."
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


def test_ingest_records_document_and_indexes_chunks(tmp_path, session, store):
    pdf = tmp_path / "notes.pdf"
    make_pdf(pdf, [GA_TEXT, "", PIZZA_TEXT])

    doc = ingest_pdf(pdf, "notes.pdf", session, store)

    saved = session.get(Document, doc.id)
    assert saved.filename == "notes.pdf"
    assert saved.page_count == 3  # the blank page still counts
    assert saved.chunk_count == 2

    results = store.search("How do genetic algorithms work?", k=2)
    assert results[0].document_id == doc.id
    assert results[0].page == 1
    assert {r.page for r in results} == {1, 3}


def test_pdf_without_text_is_rejected_and_not_saved(tmp_path, session, store):
    pdf = tmp_path / "scan.pdf"
    make_pdf(pdf, ["", ""])

    with pytest.raises(IngestError):
        ingest_pdf(pdf, "scan.pdf", session, store)

    assert session.scalar(select(func.count()).select_from(Document)) == 0


def test_invalid_pdf_is_rejected(tmp_path, session, store):
    fake = tmp_path / "fake.pdf"
    fake.write_text("this is not a pdf")

    with pytest.raises(IngestError):
        ingest_pdf(fake, "fake.pdf", session, store)


def test_failed_commit_removes_the_chunks(tmp_path, session, store, monkeypatch):
    pdf = tmp_path / "notes.pdf"
    make_pdf(pdf, [GA_TEXT])

    def broken_commit():
        raise RuntimeError("database is down")

    monkeypatch.setattr(session, "commit", broken_commit)

    with pytest.raises(RuntimeError):
        ingest_pdf(pdf, "notes.pdf", session, store)

    assert store.search("genetic algorithm") == []
