import os
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db.database import Base, make_engine
from app.db.models import Document
from app.main import app
from app.rag.chunker import Chunk
from app.rag.vectorstore import VectorStore
from app.services import cleanup
from app.services.cleanup import find_leftovers, remove_leftovers, run_startup_cleanup

KEPT = "a" * 32  # a document with a row
GONE = "b" * 32  # an id with no row: its PDF and chunks are orphans
HOUR = 3600


@pytest.fixture
def env(tmp_path):
    """A temporary database (one document, KEPT), Chroma store and upload folder."""
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(Document(id=KEPT, filename="kept.pdf", page_count=1, chunk_count=1))
    session.commit()
    store = VectorStore(path=tmp_path / "chroma")
    store.add_chunks(KEPT, [Chunk(text="Mitosis makes two cells.", page=1, index=0)])
    store.add_chunks(GONE, [Chunk(text="Orphan text.", page=1, index=0),
                            Chunk(text="More orphan text.", page=2, index=1)])
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    yield session, store, uploads
    session.close()


def make_file(path, age_seconds=0):
    path.write_bytes(b"%PDF-1.7")
    old = time.time() - age_seconds
    os.utime(path, (old, old))
    return path


def test_finds_old_temp_uploads_orphan_pdfs_and_orphan_chunks(env):
    session, store, uploads = env
    old_temp = make_file(uploads / f"upload-{'c' * 32}.pdf", age_seconds=2 * HOUR)
    make_file(uploads / f"{KEPT}.pdf")
    orphan = make_file(uploads / f"{GONE}.pdf")

    found = find_leftovers(session, uploads, store)

    assert found.temp_files == [old_temp]
    assert found.orphan_pdfs == [orphan]
    assert found.orphan_chunks == {GONE: 2}
    assert found.skipped == []


def test_find_reads_only(env):
    session, store, uploads = env
    files = [make_file(uploads / f"upload-{'c' * 32}.pdf", 2 * HOUR), make_file(uploads / f"{GONE}.pdf")]

    find_leftovers(session, uploads, store)

    assert all(f.exists() for f in files)
    assert store.chunk_counts() == {KEPT: 1, GONE: 2}


def test_remove_deletes_exactly_what_was_found(env):
    session, store, uploads = env
    old_temp = make_file(uploads / f"upload-{'c' * 32}.pdf", 2 * HOUR)
    kept_pdf = make_file(uploads / f"{KEPT}.pdf")
    orphan = make_file(uploads / f"{GONE}.pdf")

    remove_leftovers(find_leftovers(session, uploads, store), store)

    assert not old_temp.exists() and not orphan.exists()
    assert kept_pdf.exists()
    assert store.chunk_counts() == {KEPT: 1}
    assert session.get(Document, KEPT) is not None  # the database is never changed


def test_never_touches_young_temp_files_or_non_matching_names(env):
    session, store, uploads = env
    young = make_file(uploads / f"upload-{'c' * 32}.pdf", age_seconds=60)
    others = [
        make_file(uploads / "notes.pdf", 2 * HOUR),
        make_file(uploads / f"{GONE}.PDF", 2 * HOUR),  # not the exact name
        make_file(uploads / f"upload-{'c' * 32}.pdf.bak", 2 * HOUR),
        make_file(uploads / f"x{GONE}.pdf", 2 * HOUR),
    ]
    folder = uploads / f"{GONE}.pdf.d"
    folder.mkdir()
    (uploads / f"{'d' * 32}.pdf").mkdir()  # a folder with a matching name

    found = find_leftovers(session, uploads, store)
    remove_leftovers(found, store)

    assert found.temp_files == [] and found.orphan_pdfs == []
    assert young.exists() and all(p.exists() for p in others)
    assert folder.is_dir() and (uploads / f"{'d' * 32}.pdf").is_dir()


def test_an_empty_database_leaves_pdfs_and_chunks_alone(tmp_path, env):
    _, store, uploads = env
    engine = make_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    Base.metadata.create_all(engine)
    empty = sessionmaker(bind=engine)()
    old_temp = make_file(uploads / f"upload-{'c' * 32}.pdf", 2 * HOUR)
    pdf = make_file(uploads / f"{GONE}.pdf")

    found = find_leftovers(empty, uploads, store)
    remove_leftovers(found, store)

    assert found.temp_files == [old_temp]  # old temporary uploads still go
    assert found.orphan_pdfs == [] and found.orphan_chunks == {}
    assert "no documents" in found.skipped[0] and "1 PDFs and 3 chunks" in found.skipped[0]
    assert pdf.exists() and store.chunk_counts() == {KEPT: 1, GONE: 2}
    empty.close()


def test_an_unreadable_database_deletes_nothing(tmp_path, env):
    _, store, uploads = env
    # No tables: the query fails, as with a damaged or foreign database file.
    broken = sessionmaker(bind=make_engine(f"sqlite:///{tmp_path / 'broken.db'}"))()
    old_temp = make_file(uploads / f"upload-{'c' * 32}.pdf", 2 * HOUR)
    pdf = make_file(uploads / f"{GONE}.pdf")

    assert run_startup_cleanup(broken, uploads, store) is None
    assert old_temp.exists() and pdf.exists() and store.chunk_counts() == {KEPT: 1, GONE: 2}
    broken.close()


def test_a_vector_store_error_doesnt_stop_the_file_cleanup(env, monkeypatch):
    session, store, uploads = env
    orphan = make_file(uploads / f"{GONE}.pdf")

    def broken():
        raise RuntimeError("chroma is locked")

    monkeypatch.setattr(store, "chunk_counts", broken)
    found = find_leftovers(session, uploads, store)
    remove_leftovers(found, store)

    assert found.orphan_chunks == {}
    assert "vector store couldn't be read" in found.skipped[0]
    assert not orphan.exists()


@pytest.fixture
def startup(tmp_path, monkeypatch):
    """Run the app's startup hook against temporary stand-ins: the real database, upload
    folder and vector store are never opened. Returns the list of cleanup calls."""
    from app import main

    calls = []
    engine = make_engine(f"sqlite:///{tmp_path / 'startup.db'}")
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "SessionLocal", sessionmaker(bind=engine))
    monkeypatch.setattr(main, "get_upload_dir", lambda: tmp_path / "uploads")
    monkeypatch.setattr(main, "get_vector_store", lambda: "store")
    monkeypatch.setattr(main, "run_startup_cleanup", lambda *args: calls.append(args))
    return calls


def test_startup_does_nothing_while_the_setting_is_off(startup, monkeypatch):
    monkeypatch.setattr(settings, "startup_cleanup", False)

    with TestClient(app):  # `with` runs the startup hook
        pass

    assert startup == []


def test_startup_runs_the_cleanup_when_the_setting_is_on(startup, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "startup_cleanup", True)

    with TestClient(app):
        pass

    [(_, upload_dir, store)] = startup
    assert (upload_dir, store) == (tmp_path / "uploads", "store")


def test_describe_gives_counts_and_reasons_only():
    found = cleanup.Leftovers(orphan_chunks={GONE: 2}, skipped=["something"])

    assert cleanup.describe(found) == (
        "0 temporary uploads, 0 orphan PDFs, 2 orphan chunks of 1 documents; skipped: something"
    )
