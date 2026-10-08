from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, loaded from environment variables or a .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "StudyMate API"
    debug: bool = False

    # Where uploaded files and the vector database will live (git-ignored).
    data_dir: Path = Path("data")

    # Secret. Empty by default so the app can start without it for now.
    gemini_api_key: str = ""
    # Gemini model used for answers (must be a free-tier model while we're on the free tier).
    gemini_model: str = "gemini-3.8-flash"
    # Optional: used for the rest of a request when the main model returns 503. Empty = off.
    gemini_fallback_model: str = ""
    # Retries for rate limits / transient errors: the delay doubles each attempt.
    llm_max_retries: int = 3
    llm_retry_base_delay: float = 1.0
    # Give up on a single LLM request after this long.
    llm_timeout_seconds: int = 60

    # Local embedding model (downloaded once, then cached).
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    
    # Below this similarity, a question is treated as "not in the documents".
    min_similarity: float = 0.55
    # How many chunks to retrieve per question (before the similarity filter).
    retrieval_top_k: int = 5
    # Chunks where fewer than this share of characters are letters/digits
    # (e.g. text diagrams drawn with box characters) are not used as sources.
    min_alnum_ratio: float = 0.5

    # How many earlier messages (user + assistant) a follow-up question can see.
    history_window: int = 6

    # Study tools. Most LLM calls one summary/quiz/flashcard request may make (free tier).
    study_max_llm_calls: int = 8
    # Characters of document text sent in one summary call.
    study_batch_chars: int = 12000
    # Passages a quiz or flashcard set is made from.
    study_max_passages: int = 10

    # Largest PDF the upload endpoint accepts.
    max_upload_mb: int = 50

# One shared instance that the rest of the app imports.
settings = Settings()