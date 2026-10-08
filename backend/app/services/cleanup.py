"""Startup cleanup of leftovers from crashes or restarts mid-upload (Phase 9).

Two separate steps, so what would be deleted can be reported before anything is:
find_leftovers() only reads; remove_leftovers() deletes exactly what it found.

It deletes only:
1. temporary uploads: files named exactly upload-<32 hex>.pdf, older than an hour;
2. orphan PDFs: files named exactly <32 hex>.pdf whose id has no documents row;
3. orphan chunks: chunks whose document_id has no documents row.
It never changes the database, and never touches any file or folder that doesn't
match those exact names. If the database can't be read, nothing is deleted. If it
has no documents at all, only step 1 runs: an empty table more likely means a reset
or replaced database than that every PDF and chunk should go.
"""

import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Document
from app.rag.vectorstore import VectorStore

logger = logging.getLogger(__name__)

TEMP_UPLOAD = re.compile(r"upload-[0-9a-f]{32}\.pdf")
DOCUMENT_PDF = re.compile(r"[0-9a-f]{32}\.pdf")  # <document id>.pdf
# Younger temporary files are kept: another process may still be writing one.
TEMP_MIN_AGE_SECONDS = 3600


@dataclass
class Leftovers:
    """What find_leftovers found, and which parts it had to skip (with the reason)."""

    temp_files: list[Path] = field(default_factory=list)
    orphan_pdfs: list[Path] = field(default_factory=list)
    orphan_chunks: dict[str, int] = field(default_factory=dict)  # document id -> chunks
    skipped: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (self.temp_files or self.orphan_pdfs or self.orphan_chunks)


def _files_matching(upload_dir: Path, pattern: re.Pattern) -> list[Path]:
    """Files (never folders) in upload_dir whose whole name matches the pattern."""
    if not upload_dir.is_dir():
        return []
    return sorted(p for p in upload_dir.iterdir() if p.is_file() and pattern.fullmatch(p.name))


def find_leftovers(
    session: Session, upload_dir: Path, store: VectorStore, now: float | None = None
) -> Leftovers | None:
    """Everything the cleanup would delete. Reads only. None if the database can't be read."""
    try:
        known_ids = set(session.scalars(select(Document.id)))
    except Exception as exc:
        logger.warning("Startup cleanup skipped: database unreadable (%s)", type(exc).__name__)
        return None

    now = time.time() if now is None else now
    found = Leftovers(
        temp_files=[
            p for p in _files_matching(upload_dir, TEMP_UPLOAD)
            if now - p.stat().st_mtime > TEMP_MIN_AGE_SECONDS
        ]
    )

    pdfs = _files_matching(upload_dir, DOCUMENT_PDF)
    try:
        chunk_counts = store.chunk_counts()
    except Exception as exc:
        chunk_counts = None
        found.skipped.append(f"chunks: the vector store couldn't be read ({type(exc).__name__})")

    if not known_ids:
        chunks = sum(chunk_counts.values()) if chunk_counts else 0
        found.skipped.append(
            f"the database has no documents: leaving {len(pdfs)} PDFs and {chunks} chunks untouched"
        )
        return found

    found.orphan_pdfs = [p for p in pdfs if p.stem not in known_ids]
    if chunk_counts is not None:
        found.orphan_chunks = {d: n for d, n in chunk_counts.items() if d not in known_ids}
    return found


def remove_leftovers(found: Leftovers, store: VectorStore) -> None:
    """Delete exactly what find_leftovers found. A failure on one item doesn't stop the rest."""
    for path in found.temp_files + found.orphan_pdfs:
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("Could not delete %s: %s", path.name, type(exc).__name__)
    for document_id in found.orphan_chunks:
        try:
            store.delete_document(document_id)
        except Exception as exc:
            logger.warning("Could not delete chunks of %s: %s", document_id, type(exc).__name__)


def describe(found: Leftovers) -> str:
    """A one-line summary for the log: counts and names only, never content."""
    chunks = sum(found.orphan_chunks.values())
    parts = [
        f"{len(found.temp_files)} temporary uploads",
        f"{len(found.orphan_pdfs)} orphan PDFs",
        f"{chunks} orphan chunks of {len(found.orphan_chunks)} documents",
    ]
    text = ", ".join(parts)
    if found.skipped:
        text += "; skipped: " + "; ".join(found.skipped)
    return text


def run_startup_cleanup(session: Session, upload_dir: Path, store: VectorStore) -> Leftovers | None:
    """Find and delete leftovers, and log what happened. Called at startup when enabled."""
    found = find_leftovers(session, upload_dir, store)
    if found is None:
        return None
    remove_leftovers(found, store)
    logger.info("Startup cleanup removed %s", describe(found))
    return found
