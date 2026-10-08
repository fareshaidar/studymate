"""SQLite connection settings. Every test uses a temporary database file, never data/."""

import logging
import sqlite3

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db.database import Base, foreign_key_violations, make_engine
from app.db.models import Conversation, Message
from app.main import app


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "test.db"
    engine = make_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    yield path, engine
    engine.dispose()


def pragma(engine, name):
    with engine.connect() as connection:
        return connection.exec_driver_sql(f"PRAGMA {name}").scalar()


def test_every_connection_has_foreign_keys_wal_and_a_busy_timeout(db):
    _, engine = db

    assert pragma(engine, "foreign_keys") == 1
    assert pragma(engine, "journal_mode") == "wal"
    assert pragma(engine, "busy_timeout") == 10_000  # milliseconds


def test_a_message_for_a_missing_conversation_is_refused(db):
    _, engine = db
    with sessionmaker(bind=engine)() as session:
        session.add(Message(conversation_id="no-such-conversation", role="user", content="Hi"))
        with pytest.raises(IntegrityError):
            session.commit()


def test_deleting_a_conversation_still_removes_its_messages(db):
    _, engine = db
    Session = sessionmaker(bind=engine)
    with Session() as session:
        conversation = Conversation(title="Mitosis")
        conversation.messages = [Message(role="user", content="What is mitosis?")]
        session.add(conversation)
        session.commit()
        session.delete(conversation)
        session.commit()  # no foreign key error: the ORM deletes the messages first

        assert session.query(Message).count() == 0


def add_orphan_message(path):
    """A row that breaks the foreign key, written the old way (foreign keys off)."""
    connection = sqlite3.connect(path)
    connection.execute(
        "INSERT INTO messages (conversation_id, role, content, created_at) "
        "VALUES ('gone', 'user', 'old orphan', '2026-10-01 10:00:00')"
    )
    connection.commit()
    connection.close()


def test_foreign_key_violations_counts_old_rows_without_changing_them(db):
    path, engine = db
    add_orphan_message(path)

    assert foreign_key_violations(engine) == 1
    assert foreign_key_violations(engine) == 1  # still there: nothing was removed


def test_startup_logs_old_violations_and_leaves_them(db, monkeypatch, caplog):
    from app import main

    path, engine = db
    add_orphan_message(path)
    # The startup hook runs against the temporary database, never data/.
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(settings, "startup_cleanup", False)

    with caplog.at_level(logging.WARNING, logger="app.main"):
        with TestClient(app):  # `with` runs the startup hook
            pass

    assert "1 existing rows break a foreign key" in caplog.text
    assert foreign_key_violations(engine) == 1
