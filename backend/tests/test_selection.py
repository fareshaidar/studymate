from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import sessionmaker

from app.db.database import Base, make_engine
from app.db.models import Document
from app.rag.vectorstore import StoredChunk
from app.services.selection import (
    UnknownDocumentError,
    evenly_spaced,
    resolve_documents,
    usable,
)


@pytest.fixture
def session(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as session:
        for doc_id, day in [("old", 1), ("new", 2)]:
            session.add(
                Document(
                    id=doc_id,
                    filename=f"{doc_id}.pdf",
                    page_count=1,
                    chunk_count=1,
                    created_at=datetime(2026, 10, day, tzinfo=timezone.utc),
                )
            )
        session.commit()
        yield session


@pytest.mark.parametrize("document_ids", [None, []])
def test_no_selection_means_all_documents_newest_first(session, document_ids):
    assert list(resolve_documents(session, document_ids).items()) == [
        ("new", "new.pdf"),
        ("old", "old.pdf"),
    ]


def test_selection_limits_documents(session):
    assert resolve_documents(session, ["old"]) == {"old": "old.pdf"}


def test_unknown_document_raises(session):
    with pytest.raises(UnknownDocumentError) as info:
        resolve_documents(session, ["old", "nope"])
    assert info.value.missing == ["nope"]


def chunk(text, index=0):
    return StoredChunk(text=text, page=1, document_id="doc1", chunk_index=index)


def test_usable_drops_diagrams_and_strips_diagram_chars():
    diagram = chunk("┌──────┐ │ A │ └──┬───┘ ↓ ┌────┐ │ B │ └────┘", 0)
    mixed = chunk("│ Step one │ ↓ The algorithm stops after twenty stale generations.", 1)

    result = usable([diagram, mixed])

    assert [c.chunk_index for c in result] == [1]
    assert result[0].text == "Step one The algorithm stops after twenty stale generations."


@pytest.mark.parametrize(
    ("n", "expected"),
    [
        (2, [2, 7]),
        (5, [1, 3, 5, 7, 9]),
        (1, [5]),
        (10, list(range(10))),
        (20, list(range(10))),
        (0, []),
    ],
)
def test_evenly_spaced(n, expected):
    assert evenly_spaced(list(range(10)), n) == expected
