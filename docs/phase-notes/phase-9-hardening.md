# Phase 9: Hardening (in progress)

Started as a record of each step while the phase runs; the wrap-up step completes it with the
remaining steps, how the pieces connect, and 5 interview questions with answers.

## Step 1: retrieval_top_k 8 by default (`d1b6b02`)

- **Why:** the Phase 7 top_k 8 experiment answered 3 of the 5 traced false refusals (sky-04,
  sky-13, fu-06) with no unanswerable question answered. The owner had hit sky-04 in the live
  app.
- **Change:** `retrieval_top_k` 5 → 8 in `app/config.py`, with a corrected comment: it is the
  most passages an answer is built from, chosen after the similarity filter. A test pins the
  code default.
- **Docs:** the baseline numbers are labelled as measured at top_k 5, and the README table has
  top_k 8 columns from the experiment. No evaluation re-run, 0 Gemini calls.

## Investigation: the live Skylab question was still refused

"How was drinking water stored on the Skylab orbital workshop?" was refused at top_k 8. A
read-only probe of the live index with the app's own `retrieve()` (0 Gemini calls) showed:

- **The refusal came from retrieval, not the model.** The water-system passage (page 30) was
  not among the 8 passages kept, nor in the top 60 results.
- **The wording was the difference.** The dataset's wording ("…stored in the Orbital
  Workshop?") puts that passage 8th, just kept (0.660 against 0.656 for 9th). The owner's
  wording adds "Skylab", which nearly every passage of that report mentions, so general
  passages outrank it.
- **2 of the 8 slots went to front matter** (the table of contents and the list of figures),
  for both wordings.

## Step 2: retrieval robustness

### 2a. A front-matter rule behind a setting (`ae5c324`)

- **The rule** (`rag/text_quality.is_front_matter`): at least 5 dot leaders ("Title ....... 42",
  OCR-spaced dots allowed) and at least one per 18 words, counting only words that contain a
  letter or digit.
- **Why 18:** on the Skylab report, the sparsest real contents chunk has one leader per 14.2
  words, and the densest other chunk (an OCR diagram on page 55) one per 21.1. 18 sits about
  halfway, with a margin of about one leader on each side. A "TABLE OF CONTENTS" heading alone
  was rejected as a signal: "contents" also appears in prose.
- **Where it applies:** `is_usable()`, used by chat retrieval, the study tools and the
  evaluation, when `exclude_front_matter` is on.

### 2b. Reworded questions (`1c2461e`)

- 31 rewordings, one per answerable tuning item, in a separate `"reworded"` section of the
  dataset. Each takes its ground truth from the item it rewords.
- Written by Claude from the question and reference answer, without the evidence quotes or the
  PDF, avoiding the documents' own terms; reviewed by the owner, who had three rewritten so they
  don't hint at the answer and ask the same thing as the original.
- `rw-sky-04` is the owner's own wording from the live app, the only real-user wording.
- Validation rejects held-out or non-answerable originals, unchanged questions, duplicates and
  id clashes. The held-out items are untouched.

### 2c. Measurement (`6675e5b`, report `801ed6e`)

Retrieval only, 0 Gemini calls, at threshold 0.55 and top_k 8. Each ranked chunk records a
front-matter flag, so one search per question gives the numbers with the filter off and on.

| | Tuning off | Tuning on | Reworded off | Reworded on | Held-out off | Held-out on |
|---|---|---|---|---|---|---|
| hit@8 | 37/39 | 37/39 | 22/31 | 22/31 | 5/6 | 5/6 |
| hit@5 | 34/39 | 34/39 | 21/31 | 22/31 | 5/6 | 5/6 |
| Expected page kept | 37/39 | 37/39 | 22/31 | 22/31 | 5/6 | 5/6 |
| Front-matter slots / kept slots | 11/312 | 0/312 | 7/248 | 0/248 | 0/48 | 0/48 |
| Questions with ≥1 front-matter slot | 9/39 | 0/39 | 5/31 | 0/31 | 0/6 | 0/6 |

- **Flagged-chunk audit:** 20 chunks, all on the Skylab report's contents and list pages
  (13–23), none on a page a tuning or held-out question expects; none in the camera report or
  IPCC. The audit with text stays in the git-ignored results folder; the committed report holds
  pages, scores and counts only.
- **Rewording is the real gap:** 37/39 in the top 8 as worded in the dataset, 22/31 reworded.
- **Run-to-run variation:** a second run on the same code matched everywhere except the
  best-score range of the 2 held-out off-topic questions (0.467–0.501 vs 0.501–0.504). Chroma's
  search is approximate (HNSW) and the index is rebuilt each run, so low-scoring questions with
  no close match can get slightly different nearest neighbours. No count changed.

### 2d. Decision: the filter stays off

- **The rule, fixed before measuring:** default on only if, on the tuning sets, (1) "expected
  page kept" doesn't drop, (2) it or hit@8 improves in at least one set, and (3) no flagged chunk
  is on an expected page.
- **Result:** (1) and (3) are met, (2) is not: only hit@5 on the reworded set improves
  (21 → 22). Where the filter helped (sky-04 as worded in the dataset: its answer passage moves
  from 8th to 6th among the kept passages), the answer page was already kept; where retrieval
  failed, the answer page ranked too low for the freed slots to reach it.
- **The owner chose to follow the rule:** `exclude_front_matter` stays `False`. It can be turned
  on in `.env`. An answer evaluation (Gemini calls) could show whether less noise improves the
  answers.
- **Future work** (README): keyword or hybrid search, a re-ranker, smaller or section-aware
  chunks, each measured the same way.

## Step 3: API key and quota handling

- **`GET /health`** now also returns `llm_configured`: whether a Gemini key is set, as a
  boolean only (never the key). It doesn't call the LLM, so a wrong key still shows true; the
  first real request reports that with its own message.
- **Amber banner** when the key is missing: "The AI isn't set up yet: add GEMINI_API_KEY=<your
  key> to backend/.env, then restart the backend. Uploading and browsing still work; questions
  and study tools need the key." It uses the same re-checks as the offline banner (every 30 s,
  on returning to the tab, "Check now"). An older backend without the field raises no warning.
- **A key needs a restart.** `settings` reads `backend/.env` once at startup; the comment in
  `deps.py` that claimed otherwise was corrected. (A `.env` re-read was considered and declined
  by the owner, in favour of the plain "restart the backend" instruction.)
- **Daily quota → 429**, with no `Retry-After` and the message "…Please try again tomorrow.",
  for chat and the study tools (shared error handler). The UI offers no Retry on a 429. A
  per-minute limit stays 503 with `Retry-After` and the countdown.

## Step 4: uploads

- **Early size check.** FastAPI reads the whole multipart body before the upload endpoint runs,
  so the 50 MB byte count only fired after the full file had arrived. A middleware
  (`api/upload_limit.py`) now answers 413 from the `Content-Length` header first (limit plus
  1 MB for the multipart wrapping); the byte count stays as the exact check. Live check: a
  60 MB upload got its 413 in about 2 ms with 0 bytes sent (curl waits for the server's go-ahead
  before sending a large body).
- **In the UI,** `/health` reports `max_upload_mb` and the drop zone refuses a larger file before
  sending it, with the backend's message. With an older backend (no field), only the backend
  checks.
- **Batched Chroma adds.** Chunks are embedded and added 500 at a time, below Chroma's maximum
  batch size, with fewer embeddings in memory at once. A failed batch is cleaned up by
  `ingest_pdf`, which deletes the document's chunks on any error.

## Step 5: unreadable PDFs and "indexed N of M pages"

- **Every unreadable file is a clear 422**, shown in the drop zone: an empty file ("The file is
  empty."), a password-protected PDF ("…Remove the password and upload it again.", via
  `needs_pass`; it used to be a 500), a damaged or non-PDF file ("The file is not a valid
  PDF."), and any other PyMuPDF read error ("This PDF could not be read."; only the error type
  is logged). The catch-all covers reading only, so a database or Chroma failure still
  surfaces as a server error.
- **A Windows bug found by the new tests:** when PyMuPDF fails while opening a damaged file
  by name, it can keep the file open until garbage collection, and Windows can't delete an
  open file. The upload's cleanup then raised, turning the 422 into a 500 and leaving the
  temporary file behind. The parser now opens PDFs from their bytes, and a failed cleanup is
  logged instead of raised. Live check: a damaged and an empty upload both return 422 and
  leave no temporary file.
- **"Indexed N of M pages."** `ingest_pdf` returns an `IngestResult` with the number of pages
  that had text; `POST /documents` adds `text_page_count` to its response (an added field;
  `GET /documents` is unchanged, since the count isn't stored: no migrations). The drop zone
  shows "Indexed notes.pdf: text found on 12 of 20 pages." and, when pages are missing, "The
  other pages may be scanned images; their text can't be searched."

## Step 6: error handling

- **A catch-all handler** turns any unexpected exception into a JSON 500, "Something went wrong
  on the server. Please try again." with code `internal_error`, instead of Starlette's plain
  text. The log gets the method, path and error type (the server also logs the traceback);
  never the request body.
- **A stable `code` next to `detail`** for the 404s the UI acts on: `document_not_found`
  ("One or more of the selected documents no longer exist.", chat and study tools) and
  `conversation_not_found` ("This conversation no longer exists."). The messages no longer echo
  ids from the request; the missing document ids go to the log.
- **In the UI,** `ApiError` carries the code. On `document_not_found`, chat and the study panels
  ask `App` to reload the document list, which drops the stale ticks; the notice adds "The
  document list has been refreshed; please try again." and offers neither Retry nor "Start a
  new chat" (which wouldn't help). `conversation_not_found` keeps "Start a new chat"; an
  unexpected 500 shows the friendly message with Retry.

## Step 7: startup cleanup (off by default)

- **What it deletes, only:** files in `data/uploads/` named exactly `upload-<32 hex>.pdf` and
  older than an hour (interrupted uploads); files named exactly `<32 hex>.pdf` whose id has no
  `documents` row (orphan PDFs); Chroma chunks whose `document_id` has no row (orphan chunks).
- **What it never touches:** the database (it only reads the ids), any file or folder whose
  name doesn't match exactly, and anything outside `data/uploads/` and the chunk collection.
- **Safety rules:** an unreadable database means nothing is deleted; a database with no
  documents means only old temporary uploads go (PDFs and chunks are left alone, since an
  empty table more likely means a reset database); a vector store error skips the chunks but
  not the files. `find_leftovers()` only reads, `remove_leftovers()` deletes exactly that list.
- **Off by default** (`startup_cleanup = False`), by the owner's decision: it is turned on
  only after reviewing a report-only run. That run on the real data (3 documents, 3 PDFs,
  746 chunks) found 0 temporary uploads, 0 orphan PDFs and 0 orphan chunks, and changed
  nothing.

## Step 8: study time budget

- **The summary** is the only study tool that can take long: up to 7 batch calls plus a combine,
  one after another, each up to 60 s plus retries. Quiz and flashcards make at most 2 calls.
- **The rule** (`study_max_seconds`, default 180): before each batch call after the first, the
  summary checks how long it has been running; past the budget it starts no more batch calls,
  combines what is done (no combine call if only one batch finished) and marks the result
  truncated. A running call is never cut off, so the overrun is at most one batch call plus the
  combine. The "Based on" pages list only the batches actually summarised.
- **The UI warning** now reads "…to stay within the AI call or time limit."
- **Tests** use a fake clock that advances only when a fake LLM call "takes" time: 0 Gemini
  calls, instant runs.
