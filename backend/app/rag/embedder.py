from functools import lru_cache

from sentence_transformers import SentenceTransformer

from app.config import settings

# BGE models work better for search if the *question* gets this prefix.
# The documents (chunks) are embedded without it.
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


@lru_cache(maxsize=1)
def _get_model() -> SentenceTransformer:
    """Load the model once and reuse it (loading takes a few seconds)."""
    return SentenceTransformer(settings.embedding_model)


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed document chunks. Returns one vector (list of floats) per text."""
    if not texts:
        return []
    vectors = _get_model().encode(texts, normalize_embeddings=True, batch_size=32)
    return vectors.tolist()


def embed_query(query: str) -> list[float]:
    """Embed a user question for searching."""
    vector = _get_model().encode(QUERY_PREFIX + query, normalize_embeddings=True)
    return vector.tolist()