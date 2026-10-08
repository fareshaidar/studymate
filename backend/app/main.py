from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import chat, conversations, documents
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
register_error_handlers(app)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
