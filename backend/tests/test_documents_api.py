import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_db, get_upload_dir, get_vector_store
from app.config import settings
from app.db.database import Base, make_engine
from app.main import app
from app.rag.vectorstore import VectorStore
from tests.helpers import make_pdf

GA_TEXT = "A genetic algorithm evolves a population of solutions using mutation."


@pytest.fixture
def env(tmp_path):
    """Point the API at a throwaway database, vector store and upload folder."""
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    store = VectorStore(path=tmp_path / "chroma")
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()

    def override_db():
        with Session() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_vector_store] = lambda: store
    app.dependency_overrides[get_upload_dir] = lambda: upload_dir
    # No `with`: skips the startup hook, which would touch the real database.
    yield TestClient(app), store, upload_dir
    app.dependency_overrides.clear()


def upload(client, path, name=None):
    with path.open("rb") as f:
        return client.post(
            "/documents", files={"file": (name or path.name, f, "application/pdf")}
        )


def test_upload_indexes_pdf_and_lists_it(tmp_path, env):
    client, store, upload_dir = env
    pdf = tmp_path / "notes.pdf"
    make_pdf(pdf, [GA_TEXT, ""])

    response = upload(client, pdf)

    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == "notes.pdf"
    assert body["page_count"] == 2
    assert body["chunk_count"] == 1
    assert (upload_dir / f"{body['id']}.pdf").exists()
    assert store.search("genetic algorithm")[0].document_id == body["id"]

    listed = client.get("/documents").json()
    assert [d["id"] for d in listed] == [body["id"]]


def test_non_pdf_is_rejected(tmp_path, env):
    client, _, upload_dir = env
    txt = tmp_path / "notes.txt"
    txt.write_text(GA_TEXT)

    response = upload(client, txt)

    assert response.status_code == 400
    assert list(upload_dir.iterdir()) == []


def test_pdf_without_text_is_rejected_and_not_kept(tmp_path, env):
    client, _, upload_dir = env
    pdf = tmp_path / "scan.pdf"
    make_pdf(pdf, ["", ""])

    response = upload(client, pdf)

    assert response.status_code == 422
    assert list(upload_dir.iterdir()) == []
    assert client.get("/documents").json() == []


def test_too_large_upload_is_rejected(tmp_path, env, monkeypatch):
    client, _, upload_dir = env
    monkeypatch.setattr(settings, "max_upload_mb", 0)
    pdf = tmp_path / "notes.pdf"
    make_pdf(pdf, [GA_TEXT])

    response = upload(client, pdf)

    assert response.status_code == 413
    assert list(upload_dir.iterdir()) == []


def test_delete_removes_row_chunks_and_file(tmp_path, env):
    client, store, upload_dir = env
    pdf = tmp_path / "notes.pdf"
    make_pdf(pdf, [GA_TEXT])
    doc_id = upload(client, pdf).json()["id"]

    response = client.delete(f"/documents/{doc_id}")

    assert response.status_code == 204
    assert client.get("/documents").json() == []
    assert store.search("genetic algorithm") == []
    assert not (upload_dir / f"{doc_id}.pdf").exists()


def test_delete_unknown_document_returns_404(env):
    client, _, _ = env

    assert client.delete("/documents/does-not-exist").status_code == 404
