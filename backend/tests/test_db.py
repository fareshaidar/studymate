from sqlalchemy.orm import sessionmaker

from app.db.database import Base, make_engine
from app.db.models import Document


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