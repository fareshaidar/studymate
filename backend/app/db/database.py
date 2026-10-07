from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    """Parent class of every database table class."""


def make_engine(url: str | None = None):
    """Create the connection to the database (default: a SQLite file in data/)."""
    if url is None:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        url = f"sqlite:///{settings.data_dir / 'studymate.db'}"
    # check_same_thread=False: FastAPI handles requests in different threads.
    return create_engine(url, connect_args={"check_same_thread": False})


engine = make_engine()
SessionLocal = sessionmaker(bind=engine)