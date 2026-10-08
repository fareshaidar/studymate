from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

# Wait up to this long when another connection holds the write lock, instead of failing
# at once with "database is locked". (Python's sqlite3 default is 5 s.)
BUSY_TIMEOUT_SECONDS = 10


class Base(DeclarativeBase):
    """Parent class of every database table class."""


def _configure_connection(dbapi_connection, _connection_record) -> None:
    """Run on every new SQLite connection, before it is used.

    - foreign_keys=ON: SQLite ignores foreign keys unless each connection switches
      them on. Then a message can't be saved for a conversation that no longer
      exists. Existing rows aren't checked; see foreign_key_violations().
    - journal_mode=WAL: reads don't wait for a write to finish. Stored in the file
      itself, with two helper files next to it (-wal, -shm); undo with
      PRAGMA journal_mode=DELETE.
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


def make_engine(url: str | None = None):
    """Create the connection to the database (default: a SQLite file in data/)."""
    if url is None:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        url = f"sqlite:///{settings.data_dir / 'studymate.db'}"
    # check_same_thread=False: FastAPI handles requests in different threads.
    engine = create_engine(
        url, connect_args={"check_same_thread": False, "timeout": BUSY_TIMEOUT_SECONDS}
    )
    event.listen(engine, "connect", _configure_connection)
    return engine


def foreign_key_violations(engine) -> int:
    """How many existing rows break a foreign key. Reads only; changes nothing.

    Switching foreign keys on doesn't check rows that already exist, so startup
    calls this to make any such rows visible in the log.
    """
    with engine.connect() as connection:
        return len(connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall())


engine = make_engine()
SessionLocal = sessionmaker(bind=engine)
