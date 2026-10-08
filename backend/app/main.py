from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import chat, conversations, documents, study
from app.api.errors import register_error_handlers
from app.api.upload_limit import reject_oversized_uploads
from app.config import settings
from app.db import models  # noqa: F401  (registers the tables on Base)
from app.api.deps import get_upload_dir, get_vector_store
from app.db.database import Base, SessionLocal, engine
from app.services.cleanup import run_startup_cleanup


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Create any missing tables at startup (no migrations yet).
    Base.metadata.create_all(engine)
    if settings.startup_cleanup:
        with SessionLocal() as session:
            run_startup_cleanup(session, get_upload_dir(), get_vector_store())
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
app.middleware("http")(reject_oversized_uploads)


@app.get("/health")
def health_check() -> dict[str, str | bool | int]:
    """Liveness, plus what the UI needs to warn early: whether an LLM API key is set,
    and the largest upload accepted (so too-large files are refused before sending).

    The key is reported as a boolean only: never the key or any part of it. It doesn't
    call the LLM, so a key that is set but wrong still shows true (the first real
    request reports that clearly).
    """
    return {
        "status": "ok",
        "llm_configured": bool(settings.gemini_api_key),
        "max_upload_mb": settings.max_upload_mb,
    }
