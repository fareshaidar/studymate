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

    # Largest PDF the upload endpoint accepts.
    max_upload_mb: int = 50

# One shared instance that the rest of the app imports.
settings = Settings()