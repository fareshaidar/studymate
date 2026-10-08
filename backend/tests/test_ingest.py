import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.db.database import Base, make_engine
from app.db.models import Document
from app.rag.vectorstore import VectorStore
from app.services import ingest
from app.services.ingest import IngestError, ingest_pdf
from tests.helpers import make_password_pdf, make_pdf

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

    result = ingest_pdf(pdf, "notes.pdf", session, store)
    doc = result.document

    saved = session.get(Document, doc.id)
    assert saved.filename == "notes.pdf"
    assert saved.page_count == 3  # the blank page still counts
    assert saved.chunk_count == 2
    assert result.text_page_count == 2  # but has no text

    results = store.search("How do genetic algorithms work?", k=2)
    assert results[0].document_id == doc.id
    assert results[0].page == 1
    assert {r.page for r in results} == {1, 3}


def test_chunk_size_can_be_chosen(tmp_path, session, store):
    # One sentence per line: insert_text doesn't wrap, and the chunker rejoins the lines.
    page = "\n".join(f"Sentence number {i} is about genetic algorithms." for i in range(40))
    pdf = tmp_path / "notes.pdf"
    make_pdf(pdf, [page])

    default = ingest_pdf(pdf, "default.pdf", session, store).document
    small = ingest_pdf(pdf, "small.pdf", session, store, max_chars=300, overlap_chars=50).document

    assert small.chunk_count > default.chunk_count
    assert all(len(c.text) <= 300 for c in store.get_chunks(small.id))


def test_pdf_without_text_is_rejected_and_not_saved(tmp_path, session, store):
    pdf = tmp_path / "scan.pdf"
    make_pdf(pdf, ["", ""])

    with pytest.raises(IngestError):
        ingest_pdf(pdf, "scan.pdf", session, store)

    assert session.scalar(select(func.count()).select_from(Document)) == 0


def test_invalid_pdf_is_rejected(tmp_path, session, store):
    fake = tmp_path / "fake.pdf"
    fake.write_text("this is not a pdf")

    with pytest.raises(IngestError, match="not a valid PDF"):
        ingest_pdf(fake, "fake.pdf", session, store)


def test_empty_file_is_rejected(tmp_path, session, store):
    empty = tmp_path / "empty.pdf"
    empty.write_bytes(b"")

    with pytest.raises(IngestError, match="The file is empty"):
        ingest_pdf(empty, "empty.pdf", session, store)


def test_password_protected_pdf_is_rejected_with_a_clear_reason(tmp_path, session, store):
    locked = tmp_path / "locked.pdf"
    make_password_pdf(locked)

    with pytest.raises(IngestError, match="password-protected"):
        ingest_pdf(locked, "locked.pdf", session, store)
    assert session.scalar(select(func.count()).select_from(Document)) == 0


def test_any_other_read_error_becomes_a_friendly_ingest_error(tmp_path, session, store, monkeypatch):
    pdf = tmp_path / "notes.pdf"
    make_pdf(pdf, [GA_TEXT])

    def broken_extract(path):
        raise RuntimeError("internal PyMuPDF detail")

    monkeypatch.setattr(ingest, "extract_pages", broken_extract)

    with pytest.raises(IngestError, match="could not be read") as info:
        ingest_pdf(pdf, "notes.pdf", session, store)
    assert "internal PyMuPDF detail" not in str(info.value)


def test_failed_commit_removes_the_chunks(tmp_path, session, store, monkeypatch):
    pdf = tmp_path / "notes.pdf"
    make_pdf(pdf, [GA_TEXT])

    def broken_commit():
        raise RuntimeError("database is down")

    monkeypatch.setattr(session, "commit", broken_commit)

    with pytest.raises(RuntimeError):
        ingest_pdf(pdf, "notes.pdf", session, store)

    assert store.search("genetic algorithm") == []
