import shutil
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_upload_dir, get_vector_store
from app.api.upload_limit import too_large_message
from app.config import settings
from app.db.models import Document
from app.rag.vectorstore import VectorStore
from app.services.ingest import IngestError, ingest_pdf

router = APIRouter(prefix="/documents", tags=["documents"])

_COPY_CHUNK = 1024 * 1024  # copy uploads 1 MB at a time


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    page_count: int
    chunk_count: int
    created_at: datetime


def _save_upload(upload: UploadFile, dest: Path, max_bytes: int) -> None:
    """Stream the upload to disk, stopping as soon as it gets too large."""
    written = 0
    with dest.open("wb") as out:
        while block := upload.file.read(_COPY_CHUNK):
            written += len(block)
            if written > max_bytes:
                # The exact check; upload_limit's middleware already refused most
                # oversized uploads from their Content-Length, before reading them.
                raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, too_large_message())
            out.write(block)


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
def upload_document(
    file: UploadFile,
    session: Session = Depends(get_db),
    store: VectorStore = Depends(get_vector_store),
    upload_dir: Path = Depends(get_upload_dir),
) -> Document:
    """Upload a PDF and index it. Plain `def`: embedding is slow and blocking."""
    filename = Path(file.filename or "").name
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only PDF files are supported.")

    tmp_path = upload_dir / f"upload-{uuid.uuid4().hex}.pdf"
    try:
        _save_upload(file, tmp_path, settings.max_upload_mb * 1024 * 1024)
        try:
            doc = ingest_pdf(tmp_path, filename, session, store)
        except IngestError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        shutil.move(tmp_path, upload_dir / f"{doc.id}.pdf")
    finally:
        tmp_path.unlink(missing_ok=True)
    return doc


@router.get("", response_model=list[DocumentOut])
def list_documents(session: Session = Depends(get_db)) -> list[Document]:
    """All uploaded documents, newest first."""
    return list(session.scalars(select(Document).order_by(Document.created_at.desc())))


@router.get("/{document_id}/file")
def get_document_file(
    document_id: str,
    session: Session = Depends(get_db),
    upload_dir: Path = Depends(get_upload_dir),
) -> FileResponse:
    """Serve the original PDF so the frontend can open it at a cited page."""
    doc = session.get(Document, document_id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found.")
    # Built from the stored id of an existing row, never from the raw URL text,
    # so a request like "../../.env" cannot reach a file outside upload_dir.
    path = upload_dir / f"{doc.id}.pdf"
    if not path.is_file():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "The PDF file for this document is missing."
        )
    # "inline" makes the browser show the PDF (so #page=n works) instead of
    # downloading it; the filename still names the tab.
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=doc.filename,
        content_disposition_type="inline",
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: str,
    session: Session = Depends(get_db),
    store: VectorStore = Depends(get_vector_store),
    upload_dir: Path = Depends(get_upload_dir),
) -> Response:
    """Delete a document: its database row, its chunks and its stored file."""
    doc = session.get(Document, document_id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found.")
    # Row first: once it's gone the document is invisible to the app, so a
    # failure below only leaves orphaned chunks/files, never a broken document.
    session.delete(doc)
    session.commit()
    store.delete_document(document_id)
    (upload_dir / f"{document_id}.pdf").unlink(missing_ok=True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
