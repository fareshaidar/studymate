# Phase 9: Hardening

Making StudyMate behave well when things go wrong: retrieval that holds up to real wording,
clear messages for missing keys, quotas, bad files and deleted data, and safe handling of
uploads, leftovers and the database. Every step was planned, approved by the owner, tested
without Gemini calls (0 in the whole phase), and committed on its own.

| Step | Commit(s) | What |
|---|---|---|
| 1 | `d1b6b02` | `retrieval_top_k` 8 by default; baselines relabelled as measured at top_k 5 |
| 2a–2d | `ae5c324`, `1c2461e`, `6675e5b`, `801ed6e`, `bef041f` | Front-matter rule, 31 reworded questions, filter measured off/on, decision: off |
| 3 | `5ad2b5c` | Missing-key banner (`/health` `llm_configured`); daily quota → 429, no Retry |
| 4 | `373db4a` | Oversized uploads refused from `Content-Length`; batched Chroma adds |
| 5 | `c61caaf` | Empty, password-protected, damaged PDFs → 422; "indexed N of M pages"; Windows file-handle fix |
| 6 | `38a5a19` | Catch-all JSON 500; error codes; UI refreshes the list for deleted documents |
| 7 | `9cbd7e5` | Startup cleanup of leftovers (off by default; report-only run found nothing) |
| 8 | `f604b04` | Summary time budget (180 s), partial summary instead of waiting |
| 9 | `f87d2b7` | Limits on document ids, id length and file name length |
| 10 | `2ca74b2` | SQLite foreign keys, WAL, busy timeout; no more orphan messages |

Tests: 324 backend tests before Phase 8, 331 after it, **413** after Phase 9; frontend 159 →
**178**.

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

## Step 9: input limits

- **`app/api/limits.py`** defines the limits once: at most 200 `document_ids` per request, ids
  of at most 64 characters (real ones are 32), file names of at most 255 characters.
- **Ids** (chat and the three study tools; `conversation_id` too): Pydantic checks them while
  reading the request, so a request over a limit gets a 422 before any search or LLM call.
- **File names** are shortened to 255 characters, keeping the extension, rather than refused: a
  long name isn't the user's fault.
- Normal use can't reach these limits; ticking no documents (meaning all) sends no ids.

## Step 10: SQLite settings

- **Set on every connection** (`make_engine`): foreign keys on, WAL journal mode, and a 10 s busy
  timeout (Python's default was 5 s).
- **The bug it fixes:** a conversation deleted while its answer was loading used to leave the
  new messages behind as invisible orphans. With foreign keys on, that save fails, is rolled
  back, and chat answers the existing 404 `conversation_not_found`.
- **Existing data:** no row or table changes. Foreign keys only check new writes, so startup
  runs the read-only `PRAGMA foreign_key_check` and logs (never fixes) any old violating rows.
  The real database had 0 before the change (3 documents, 2 conversations, 6 messages).
- **WAL** is stored in the database file and adds `studymate.db-wal` and `studymate.db-shm`
  next to it; undo with `PRAGMA journal_mode=DELETE`. The owner backed up the database first
  (`studymate.db.bak`); all of these are under the git-ignored `backend/data/`.
- **Tests** use temporary database files only; the real database was confirmed untouched after
  the test run (no WAL files, same size and time as the backup).

## How the pieces connect

**A request's path through the new protections:**

```
browser ── UploadDropzone: refuses > max_upload_mb before sending (limit from /health)
   │
   ▼
FastAPI ── upload_limit middleware: 413 from Content-Length, before the body is read
   │      request models: ids ≤ 200 and ≤ 64 characters, else 422 (no search, no LLM call)
   ▼
endpoint ── ingest: unreadable PDF → IngestError → 422 with a clear reason
   │        chat/study: unknown documents or conversation → NotFoundError(code) → 404
   │        LLM errors → 503 + Retry-After (per minute) / 429 (daily quota) / 502 / 500
   │        anything else → catch-all → 500 "Something went wrong…" (code internal_error)
   ▼
UI ── ApiError {status, message, retryAfter, code}
      → ErrorNotice: Retry / countdown / "Start a new chat" / nothing, by status and code
      → document_not_found: chat and study panels ask App to reload the document list
```

**Startup** (`main.lifespan`): create missing tables → read-only `PRAGMA foreign_key_check`,
logging (never fixing) old violating rows → startup cleanup, only if `startup_cleanup` is on
(find, then remove exactly what was found).

**Every database connection** (`make_engine`): foreign keys on, WAL, 10 s busy timeout. With
foreign keys on, a chat answer for a conversation deleted meanwhile can't be saved: the service
rolls back and the API answers 404 `conversation_not_found`.

**`/health`** (polled every 30 s, on tab focus and on "Check now") feeds three things in the UI:
the red offline banner, the amber missing-key banner (`llm_configured`), and the upload size
check (`max_upload_mb`).

**Retrieval** (`retrieve`): search 2 × top_k (16), drop unusable chunks (diagrams; front matter
only if `exclude_front_matter` is on), keep the best 8 above `min_similarity`. The evaluation
records the front-matter flag per chunk, so one search gives the numbers with the filter off
and on.

## Settings after Phase 9

| Setting | Default | Change in Phase 9 |
|---|---|---|
| `retrieval_top_k` | 8 | was 5 (step 1) |
| `exclude_front_matter` | `False` | new; measured, kept off by the owner (step 2) |
| `max_upload_mb` | 50 | unchanged; now also enforced early and in the UI (step 4) |
| `startup_cleanup` | `False` | new; off until the owner turns it on (step 7) |
| `study_max_seconds` | 180 | new (step 8) |
| `min_similarity` | 0.55 | unchanged; 0.60 still awaits the owner's decision |

## Design tradeoffs

- **A decision rule fixed before measuring.** The front-matter filter only removed junk, but
  the rule said "on only if expected page kept or hit@8 improves on a tuning set", and neither
  did. Following the rule, even when the result is disappointing, is what keeps the evaluation
  from turning into tuning-to-the-answer. The setting stays available.
- **Honest numbers over flattering ones.** The reworded set shows 71% (22/31) instead of 95%
  (37/39) for the right page in the top 8. It is reported next to the original numbers, and the
  held-out items were never reworded or used to choose.
- **Restart over re-reading `.env`.** A key added to `.env` needs a backend restart. Re-reading
  the file while the key is missing would have avoided that, but the owner preferred the plainer
  behaviour and a banner that says exactly what to do.
- **429 for the daily quota.** It isn't "temporarily unavailable" (503): it won't come back in
  seconds, so the UI shows no Retry. The per-minute limit keeps 503 with a countdown.
- **Shorten long file names, refuse oversized files.** A long name isn't the user's fault; a
  300 MB file can't be processed, so it is refused before it is sent.
- **Open PDFs from bytes.** It costs memory (at most 50 MB per upload) but means PyMuPDF never
  holds a file open, which on Windows had turned a clean 422 into a 500.
- **Report, never repair, the database.** Old rows that break a foreign key are logged, not
  deleted; the startup cleanup never changes a row and deletes nothing if the database can't be
  read or is empty. Destructive actions need the owner's explicit decision.
- **Middleware for the size check.** FastAPI reads the whole multipart body before the
  endpoint or its dependencies run, so only a middleware sees the request before the file
  arrives. The byte count while saving stays as the exact check.

## Interview questions

1. **Q: After raising top_k to 8, a real question was still refused. How did you find out why,
   and why not just raise top_k again?**
   A: I ran the app's own `retrieve()` read-only on the live index, with no LLM calls, and
   printed the 16 passages it searched and the 8 it kept. The answer passage wasn't in the top
   60, so the model was right to refuse: the problem was retrieval. Comparing with the
   evaluation, the only difference was wording: the dataset asked "…stored in the Orbital
   Workshop?", the user asked "…on the Skylab orbital workshop?", and "Skylab" appears on nearly
   every page, which pulls in general passages. More top_k wouldn't reach rank 60, and costs
   prompt size. Instead I added 31 natural rewordings of the tuning questions: the right page
   reaches the top 8 for 95% as originally worded but 71% reworded. That gap is the honest
   finding, and it points to keyword search or a re-ranker, not a bigger top_k.

2. **Q: Your front-matter filter removed only junk. Why is it switched off?**
   A: Because I wrote down the rule for switching it on before measuring: on only if, on the
   tuning sets, "expected page kept" doesn't drop, it or hit@8 improves somewhere, and no flagged
   chunk is on an expected page. The audit was clean (20 chunks, all contents and list pages,
   none expected), and it freed 11 of 312 passage slots, but expected-page-kept and hit@8 didn't
   change: where it helped, the answer was already inside the top 8. Switching it on anyway
   would mean moving the goalposts after seeing the result. It stays as a setting, and an answer
   evaluation (which costs Gemini calls) could still show a benefit.

3. **Q: FastAPI reads the whole upload before your endpoint runs. How do you refuse a 300 MB
   file early?**
   A: Three layers. The browser checks `file.size` against the limit from `/health` and refuses
   before sending anything. On the server, a small HTTP middleware looks at `Content-Length` for
   `POST /documents` and answers 413 before the body is read; a live test showed a 60 MB upload
   refused in about 2 ms with 0 bytes sent. The exact byte count while copying the file stays as
   the backstop, for requests without `Content-Length`. The middleware allows 1 MB for the
   multipart wrapping so a file exactly at the limit isn't refused by mistake.

4. **Q: How do you make a startup cleanup that deletes files safe?**
   A: By separating finding from deleting and making every rule narrow. `find_leftovers()` only
   reads and returns a list; `remove_leftovers()` deletes exactly that list. It only matches
   exact names (`upload-<32 hex>.pdf` older than an hour, `<32 hex>.pdf` with no database row) and
   chunks with no row; it never changes the database. If the database can't be read, nothing is
   deleted; if it has no documents, only old temporary files go, because an empty table more
   likely means a reset database than "delete everything". It ships off by default, and before
   anyone turns it on, a report-only run on the real data showed it would delete nothing.

5. **Q: Tell me about a bug your tests found.**
   A: A damaged PDF upload on Windows returned 500 instead of the intended 422. Ingest correctly
   raised "not a valid PDF", but the cleanup then failed with "file in use". When PyMuPDF fails
   while opening a file by name, it keeps the file handle until garbage collection, and Windows
   can't delete an open file. The fix had two parts: open PDFs from their bytes, so no handle is
   ever held, and log a failed cleanup instead of raising it, so cleanup can never turn a clear
   answer into a 500. I confirmed it live: damaged and empty uploads both return 422 and leave no
   temporary file.
