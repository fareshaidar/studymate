from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import chat, conversations, documents, study
from app.api.errors import register_error_handlers
from app.config import settings
from app.db import models  # noqa: F401  (registers the tables on Base)
from app.db.database import Base, engine


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Create any missing tables at startup (no migrations yet).
    Base.metadata.create_all(engine)
    yield


app = FastAPI(
    title=settings.app_name,
    description="RAG-based study assistant with cited answers.",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(conversations.router)
app.include_router(study.router)
register_error_handlers(app)


@app.get("/health")
def health_check() -> dict[str, str | bool]:
    """Liveness, plus whether an LLM API key is set, so the UI can warn before a question fails.

    Only a boolean: never the key or any part of it. It doesn't call the LLM, so a key
    that is set but wrong still shows true (the first real request reports that clearly).
    """
    return {"status": "ok", "llm_configured": bool(settings.gemini_api_key)}
