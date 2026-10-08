"""The user-facing site (app/web.py): API under /api, built frontend at /.

Everything uses temporary folders and a temporary database: no request can reach
the real backend/data, and no test needs a real frontend build.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect
from sqlalchemy.orm import sessionmaker

from app.api import documents as documents_api
from app.api.deps import get_db, get_upload_dir, get_vector_store
from app.config import settings
from app.db.database import Base, make_engine
from app.main import app as api
from app.rag.vectorstore import VectorStore
from app.web import create_site


@pytest.fixture
def dist(tmp_path):
    """A stand-in for frontend/dist, as `npm run build` would make it."""
    folder = tmp_path / "dist"
    (folder / "assets").mkdir(parents=True)
    (folder / "index.html").write_text(
        '<!doctype html><title>StudyMate</title><script src="/assets/app.js"></script>',
        encoding="utf-8",
    )
    (folder / "assets" / "app.js").write_text("console.log('StudyMate');", encoding="utf-8")
    return folder


@pytest.fixture
def api_on_temp_data(tmp_path):
    """Point the API's database, vector store and upload folder at temporary ones."""
    engine = make_engine(f"sqlite:///{tmp_path / 'web.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    def override_db():
        with Session() as session:
            yield session

    uploads = tmp_path / "uploads"
    uploads.mkdir()
    api.dependency_overrides[get_db] = override_db
    api.dependency_overrides[get_vector_store] = lambda: VectorStore(path=tmp_path / "chroma")
    api.dependency_overrides[get_upload_dir] = lambda: uploads
    yield uploads
    api.dependency_overrides.clear()


def test_the_api_is_served_under_api(dist, api_on_temp_data):
    # No `with`: the startup hook isn't needed here (it has its own test below).
    client = TestClient(create_site(dist))

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert client.get("/api/documents").json() == []


def test_the_built_frontend_is_served_at_the_root(dist):
    client = TestClient(create_site(dist))

    page = client.get("/")
    script = client.get("/assets/app.js")

    assert page.status_code == 200 and "<title>StudyMate</title>" in page.text
    assert script.status_code == 200 and "javascript" in script.headers["content-type"]
    assert client.get("/no-such-file.js").status_code == 404


def test_a_missing_build_shows_how_to_build_it(tmp_path):
    client = TestClient(create_site(tmp_path / "not-built"))

    page = client.get("/")

    assert page.status_code == 200
    assert "scripts\\setup.ps1" in page.text
    assert client.get("/api/health").status_code == 200  # the API works regardless


def test_the_api_startup_runs_for_the_site(dist, tmp_path, monkeypatch):
    """A mounted app doesn't run its own startup; the site must run it."""
    from app import main

    engine = make_engine(f"sqlite:///{tmp_path / 'startup.db'}")
    monkeypatch.setattr(main, "engine", engine)  # a temporary database, never data/
    monkeypatch.setattr(settings, "startup_cleanup", False)

    with TestClient(create_site(dist)):  # `with` runs the startup hook
        pass

    assert {"documents", "conversations", "messages"} <= set(inspect(engine).get_table_names())


def test_the_early_upload_size_check_still_works_under_api(tmp_path, dist, api_on_temp_data, monkeypatch):
    uploads = api_on_temp_data
    monkeypatch.setattr(settings, "max_upload_mb", 1)

    def must_not_run(*args, **kwargs):
        raise AssertionError("the upload endpoint should not have been reached")

    # The middleware must answer before the endpoint runs. If it missed the request
    # (url.path is "/api/documents" under the mount), resolving this dependency would
    # fail with a 500, instead of the byte-count backstop quietly also giving a 413.
    api.dependency_overrides[get_upload_dir] = must_not_run
    monkeypatch.setattr(documents_api, "ingest_pdf", must_not_run)
    big = b"%PDF-1.7\n" + b"0" * (3 * 1024 * 1024)

    response = TestClient(create_site(dist), raise_server_exceptions=False).post(
        "/api/documents", files={"file": ("big.pdf", big, "application/pdf")}
    )

    assert response.status_code == 413
    assert response.json()["detail"] == "File is larger than 1 MB."
    assert list(uploads.iterdir()) == []


def test_the_developer_app_is_unchanged(api_on_temp_data):
    # uvicorn app.main:app still serves the API at the root, as before (no /api).
    client = TestClient(api)

    assert client.get("/health").status_code == 200
    assert client.get("/api/health").status_code == 404
