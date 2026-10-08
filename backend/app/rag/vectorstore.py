from dataclasses import dataclass
from pathlib import Path

import chromadb

from app.config import settings
from app.rag.chunker import Chunk
from app.rag.embedder import embed_documents, embed_query

COLLECTION_NAME = "chunks"
# Chunks embedded and added per call. Chroma rejects a single add above its maximum
# batch size (a few thousand), which a very large PDF could reach; batches also keep
# fewer embeddings in memory at once. A 398-page PDF has about 600 chunks.
ADD_BATCH_SIZE = 500


@dataclass
class SearchResult:
    """One chunk returned by a search, with everything needed for a citation."""

    text: str
    page: int
    document_id: str
    chunk_index: int
    score: float  # cosine similarity: higher = closer in meaning


@dataclass
class StoredChunk:
    """One chunk as stored, without a score (it wasn't found by a search)."""

    text: str
    page: int
    document_id: str
    chunk_index: int


class VectorStore:
    """Thin wrapper around ChromaDB so the rest of the app never touches it."""

    def __init__(self, path: Path | None = None) -> None:
        path = path or settings.data_dir / "chroma"
        path.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(path))
        # "cosine" tells Chroma to measure closeness by angle between vectors.
        self._collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME, metadata={"hnsw:space": "cosine"}
        )

    def add_chunks(self, document_id: str, chunks: list[Chunk]) -> None:
        """Embed and store the chunks of one document (replacing any old copy).

        Added in batches of ADD_BATCH_SIZE. If a batch fails, the caller (ingest_pdf)
        deletes the document's chunks again, so no half-added document stays behind.
        """
        self.delete_document(document_id)
        for start in range(0, len(chunks), ADD_BATCH_SIZE):
            batch = chunks[start : start + ADD_BATCH_SIZE]
            self._collection.add(
                ids=[f"{document_id}:{c.index}" for c in batch],
                embeddings=embed_documents([c.text for c in batch]),
                documents=[c.text for c in batch],
                metadatas=[
                    {"document_id": document_id, "page": c.page, "chunk_index": c.index}
                    for c in batch
                ],
            )

    def search(
        self, query: str, k: int = 5, document_ids: list[str] | None = None
    ) -> list[SearchResult]:
        """Return the k chunks closest in meaning to the query, best first."""
        total = self._collection.count()
        if total == 0:
            return []
        where = {"document_id": {"$in": document_ids}} if document_ids else None
        result = self._collection.query(
            query_embeddings=[embed_query(query)],
            n_results=min(k, total),
            where=where,
        )
        return [
            SearchResult(
                text=text,
                page=meta["page"],
                document_id=meta["document_id"],
                chunk_index=meta["chunk_index"],
                score=1.0 - distance,  # Chroma returns distance, we want similarity
            )
            for text, meta, distance in zip(
                result["documents"][0], result["metadatas"][0], result["distances"][0]
            )
        ]

    def get_chunks(self, document_id: str) -> list[StoredChunk]:
        """Every chunk of one document, in reading order (by chunk index, so by page)."""
        result = self._collection.get(
            where={"document_id": document_id}, include=["documents", "metadatas"]
        )
        chunks = [
            StoredChunk(
                text=text,
                page=meta["page"],
                document_id=meta["document_id"],
                chunk_index=meta["chunk_index"],
            )
            for text, meta in zip(result["documents"], result["metadatas"])
        ]
        # Chroma doesn't promise any order for `get`, so sort explicitly.
        return sorted(chunks, key=lambda c: c.chunk_index)

    def chunk_counts(self) -> dict[str, int]:
        """How many chunks each document id has in the store (reads metadata only)."""
        result = self._collection.get(include=["metadatas"])
        counts: dict[str, int] = {}
        for meta in result["metadatas"]:
            counts[meta["document_id"]] = counts.get(meta["document_id"], 0) + 1
        return counts

    def delete_document(self, document_id: str) -> None:
        """Remove every chunk that belongs to a document."""
        self._collection.delete(where={"document_id": document_id})