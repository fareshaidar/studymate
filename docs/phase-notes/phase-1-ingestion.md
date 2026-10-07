# Phase 1: PDF ingestion pipeline

## What was built

- **`POST /documents`**: upload a PDF. It is parsed, chunked, embedded, stored in ChromaDB and recorded in SQLite. Returns `201` with the document's id, filename, page count, chunk count and creation time.
- **`GET /documents`**: lists uploaded documents, newest first.
- **`DELETE /documents/{id}`**: removes the document's SQLite row, its Chroma chunks and the stored PDF.
- **`app/services/ingest.py`**: `ingest_pdf()`, the pipeline itself. It has no HTTP code, so it can be called from a script or re-index job later.
- **`app/api/deps.py`**: FastAPI dependencies for the DB session, the shared vector store and the upload folder.
- **`count_pages()`** in the parser, plus a `max_upload_mb` setting (default 50).
- Tests: `test_ingest.py` (service) and `test_documents_api.py` (HTTP, via `TestClient`). The PDF builder lives in `tests/helpers.py`. 30 tests in total.

## How the pieces connect

```
UploadFile ──► _save_upload (streamed, size-capped) ──► data/uploads/upload-<tmp>.pdf
                                                           │
                                                ingest_pdf │
     extract_pages ─► chunk_pages ─► VectorStore.add_chunks (embed_documents → Chroma)
                                   └► Document row ─► SQLite commit
                                                           │
                                       rename to data/uploads/<doc.id>.pdf
```

The `Document.id` (a UUID hex) links everything: Chroma chunk ids are `<doc_id>:<chunk_index>` with `document_id` in their metadata, and the stored file is `<doc_id>.pdf`. Search results already carry `document_id` and `page`, so the query phase can map a chunk back to its file and page for citations.

## Design decisions

- **Keep Chroma and SQLite consistent.** The Chroma add and the SQLite commit share one `try`. On any failure the session is rolled back and the chunks are deleted, so a half-indexed document can't exist.
- **Delete the row first.** `DELETE` removes the SQLite row (the source of truth for what exists), then the chunks, then the file. If a later step fails, the leftovers are orphaned chunks or files the app never shows, never a listed document with missing data.
- **User errors vs. bugs.** `IngestError` (not a valid PDF, or no extractable text such as a scanned image) maps to `422`. A wrong extension gets `400`, too large gets `413`, and anything else stays a `500`.
- **Real page count.** `extract_pages` skips blank pages but keeps the real numbers. `page_count` comes from `count_pages`, so it reports the true total.
- **Streamed upload with a size cap.** The file is copied 1 MB at a time and rejected once it passes the limit, so a huge upload is never held in memory.
- **Sync endpoint.** `upload_document` is a plain `def`, so FastAPI runs it in a threadpool and the CPU-bound embedding doesn't block the event loop.
- **Dependency injection for tests.** The DB, vector store and upload dir come from `Depends`, so tests swap in temp folders with `app.dependency_overrides` and never touch `data/`.
- **Tables at startup.** A `lifespan` hook runs `create_all`. That's enough until the schema changes, at which point Alembic would replace it.
- **Original PDFs are kept,** so documents can be re-chunked or re-embedded later without re-uploading.

## Interview questions

1. **Q: Your data lives in two stores, SQLite and ChromaDB. How do you keep them consistent without a distributed transaction?**
   A: With a compensating action. Ingest writes the chunks to Chroma first, then commits the SQLite row, both in one `try`. If either fails, I roll back the session and delete the chunks by `document_id`. Delete goes the other way: the row is removed first, because the row decides whether a document exists. A crash midway then leaves only invisible orphans, which a cleanup job could sweep up, instead of a visible but broken document.

2. **Q: Why is the upload endpoint `def` and not `async def`?**
   A: Parsing and embedding are blocking, CPU-bound calls. Inside `async def` they would freeze the event loop and stall every other request. With a plain `def`, FastAPI runs the handler in its threadpool. For heavy loads, the next step would be a background job queue that returns `202` and a status URL.

3. **Q: How do you stop someone uploading a 5 GB file?**
   A: The upload is streamed to disk in 1 MB blocks with a running byte count, and the request is rejected with `413` as soon as it passes `max_upload_mb`, deleting the partial file. In production I'd also set a body-size limit at the reverse proxy so oversized requests never reach Python.

4. **Q: Why store `page_count` separately when you already have the pages?**
   A: The parser drops pages with no text (blank or scanned pages) but keeps their real numbers, so citations stay correct. The number of extracted pages is therefore not the document's length. `count_pages` reads the real total from the PDF.

5. **Q: How do you test the API without touching real data or a real database?**
   A: Every external resource comes in through a FastAPI dependency: `get_db`, `get_vector_store` and `get_upload_dir`. Tests override them with a temp SQLite file, a temp Chroma folder and a temp upload directory under pytest's `tmp_path`. They also skip the startup hook so the real database is never created. The ingest service is tested on its own as well, including a forced commit failure that checks the chunks are cleaned up.
