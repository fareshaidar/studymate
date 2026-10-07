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
    # Local embedding model (downloaded once, then cached).
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    
    # Below this similarity, a question is treated as "not in the documents".
    min_similarity: float = 0.55

# One shared instance that the rest of the app imports.
settings = Settings()