from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.db.database import SessionLocal
from app.llm.base import LLMClient
from app.llm.gemini import GeminiClient
from app.rag.vectorstore import VectorStore


def get_db() -> Iterator[Session]:
    """One database session per request, closed when the request ends."""
    with SessionLocal() as session:
        yield session


@lru_cache(maxsize=1)
def get_vector_store() -> VectorStore:
    """One shared vector store for the whole app."""
    return VectorStore()


@lru_cache(maxsize=1)
def get_llm_client() -> LLMClient:
    """One shared LLM client, created on first use (not at startup).

    So the app still starts without an API key; only requests that need the LLM
    fail, with MissingAPIKeyError. A failed attempt isn't cached, so adding the
    key later works without restarting the app.
    """
    return GeminiClient()


def get_upload_dir() -> Path:
    """Folder where the original uploaded PDFs are kept."""
    path = settings.data_dir / "uploads"
    path.mkdir(parents=True, exist_ok=True)
    return path
