from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.db.database import Base, make_engine
from app.db.models import Conversation, Document, Message


def make_session_factory(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def test_document_can_be_saved_and_read_back(tmp_path):
    # A temporary database file, so the test never touches your real data.
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)  # creates the tables
    Session = sessionmaker(bind=engine)

    with Session() as session:
        doc = Document(filename="notes.pdf", page_count=10, chunk_count=25)
        session.add(doc)
        session.commit()
        doc_id = doc.id

    with Session() as session:
        saved = session.get(Document, doc_id)
        assert saved.filename == "notes.pdf"
        assert saved.chunk_count == 25
        assert len(saved.id) == 32


def test_conversation_keeps_messages_in_order_with_sources(tmp_path):
    Session = make_session_factory(tmp_path)
    sources = [{"n": 1, "document_id": "doc1", "filename": "ga.pdf", "page": 2}]

    with Session() as session:
        conv = Conversation(title="How do GAs work?")
        conv.messages.append(Message(role="user", content="How do GAs work?"))
        conv.messages.append(
            Message(role="assistant", content="They evolve [1].", sources=sources, reason="ok")
        )
        session.add(conv)
        session.commit()
        conv_id = conv.id

    with Session() as session:
        saved = session.get(Conversation, conv_id)
        assert [m.role for m in saved.messages] == ["user", "assistant"]
        assert saved.messages[0].sources is None
        assert saved.messages[1].sources == sources
        assert saved.messages[1].reason == "ok"


def test_deleting_a_conversation_deletes_its_messages(tmp_path):
    Session = make_session_factory(tmp_path)
    with Session() as session:
        keep = Conversation(title="keep", messages=[Message(role="user", content="a")])
        drop = Conversation(
            title="drop",
            messages=[Message(role="user", content="b"), Message(role="assistant", content="c")],
        )
        session.add_all([keep, drop])
        session.commit()

        session.delete(drop)
        session.commit()

        assert session.scalar(select(func.count()).select_from(Message)) == 1
