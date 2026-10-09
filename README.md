# StudyMate

A RAG-based study assistant. Upload your lecture notes and PDFs, ask questions,
and get answers with citations to the exact document and page. It also
generates summaries, quizzes, and flashcards from your material.

> Status: Phases 0–10 are done: the backend (ingestion, cited chat, conversations, study tools,
> evaluation), the React frontend, hardening (see [Hardening](#hardening-phase-9)) and Windows
> packaging (see [Quick start (Windows)](#quick-start-windows) and
> [the Phase 10 notes](docs/phase-notes/phase-10-packaging.md)).

Built with Claude Code as an AI pair programmer: I set the requirements, reviewed each step and made the design decisions, and the tests and evaluation were run and checked at every phase.

## Quick start (Windows)

**You need:**
- **Python 3.11** from [python.org](https://www.python.org/downloads/), with the `py` launcher
  (ticked by default in the installer);
- **Node.js 22.12 or newer**, the LTS version (22 or 24), from [nodejs.org](https://nodejs.org/);
- **a Gemini API key** from Google AI Studio.

**Then, in PowerShell, in the project folder:**

1. Set up (once; safe to run again):
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
   ```
2. Open `backend\.env` (setup creates it the first time) and put your key after the equals
   sign: `GEMINI_API_KEY=<your key>`. Setup never overwrites this file once it exists.
3. Start StudyMate (each time):
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\start.ps1
   ```
   Your browser opens at http://127.0.0.1:8000. Press Ctrl+C in that window to stop it.

Notes:
- `-ExecutionPolicy Bypass` applies to that one command only; it changes no system setting.
- The first start downloads the embedding model (about 130 MB) once, so it takes longer.
- `start.ps1` options: `-Port 8001` to use another port, `-NoBrowser` to not open the browser.
- Your documents, conversations and search index stay on your computer, in `backend\data`.
- Optional settings are listed, commented out at their defaults, in `backend\.env.example`.

## Troubleshooting

- **"running scripts is disabled on this system":** type the whole command shown above,
  including `powershell -ExecutionPolicy Bypass -File`, rather than just `scripts\setup.ps1`.
- **"Python 3.11 is not installed" or "the Python launcher 'py' was not found":** install
  Python 3.11 from python.org, then open a new PowerShell window and run setup again.
- **"Node.js was not found" or "Node.js … is too old":** install the Node.js LTS version (22 or
  24), then open a new PowerShell window and run setup again.
- **Setup fails with an EPERM error:** close npm run dev and any editor terminals in the
  frontend folder, then run setup again.
- **"port 8000 is already in use":** StudyMate (or another program) is already running there.
  Close it, or start on another port:
  `powershell -ExecutionPolicy Bypass -File scripts\start.ps1 -Port 8001`.
- **An amber banner "The AI isn't set up yet":** put your key in `backend\.env`
  (`GEMINI_API_KEY=<your key>`), then stop StudyMate with Ctrl+C and start it again.
- **The first start is slow:** the one-time embedding model download (about 130 MB).
- **"Not started: … Run setup first":** run `scripts\setup.ps1` as in step 1 above.

## Features

- PDF upload and indexing, with answers citing the exact document and page
- A "not in your documents" answer when the material doesn't cover the question
- Conversations with follow-up questions
- Summaries, quizzes and flashcards from your documents
- An evaluation suite for retrieval and answer quality (see [Evaluation](#evaluation))
- A browser UI:
  - upload with a progress bar;
  - choose which documents to search;
  - clickable citations that open the PDF at the cited page;
  - saved conversations and a Study tab;
  - keyboard and screen-reader basics, and a layout that works on narrow screens.

  See [the Phase 8 notes](docs/phase-notes/phase-8-frontend.md).

## Evaluation

StudyMate is measured with its own retrieval and chat code on 65 questions about three public
PDFs: a NASA Skylab report and a Space Telescope camera report (both OCR scans) and the IPCC AR6
Summary for Policymakers. Questions are answerable, follow-up, off-topic, or on-topic but not
answered in the documents. The PDFs are not in the repository; see
[the Phase 7 notes](docs/phase-notes/phase-7-evaluation.md) for how to run it and for the
details. Full baseline reports: [retrieval](docs/evaluation/retrieval-baseline.md) and
[answers](docs/evaluation/answer-baseline.md).

- **Tuning set:** 55 questions, used to choose settings.
- **Held-out set:** 10 questions by the project owner, never used to choose settings.

Measured with similarity threshold 0.55 and 1800-character chunks, at top_k 5 (the default
until Phase 9) and top_k 8 (the default since Phase 9; see the [top_k 8
experiment](#top_k-8-experiment)). Counts are shown because n is small.

| | Tuning, top_k 5 | Tuning, top_k 8 | Held-out, top_k 5 | Held-out, top_k 8 |
|---|---|---|---|---|
| Right page ranked first (hit@1) | 24/39 | 24/39 | 3/6 | 3/6 |
| Right page in the top 5 (hit@5) | 34/39 | 34/39 | 5/6 | 5/6 |
| Answerable questions wrongly refused | 4/39 | 1/39 | 1/6 | 1/6 |
| Off-topic questions refused | 8/8 | 8/8 | 2/2 | 2/2 |
| On-topic questions not in the documents refused | 8/8 | 8/8 | 2/2 | 2/2 |
| Answers with at least one correct page citation | 34/35 | 36/38 | 5/5 | 5/5 |
| Claims supported by the cited passages (LLM judge) | 46/46 | 53/53 | 5/5 | 5/5 |

The first two rows count answerable questions plus follow-ups, and follow-ups are searched as
their intended standalone question. They measure the ranking, which top_k doesn't change, so
they are the same in both columns. The top_k 8 answer numbers come from the experiment below,
a full run on all 65 questions.

**Main findings**
- **Off-topic questions** score low and are mostly stopped by the similarity threshold.
- **On-topic questions** whose answer isn't in the documents score in the same range as many
  answerable ones (0.61–0.71 vs 0.62–0.81), so no threshold separates them. The model's "not found" rule refused all 10.
- **All 5 false refusals at top_k 5 (4 tuning, 1 held-out) were traced.** In every one, the
  passage containing the answer was not among the 5 shown to the model, so declining was correct. The
  answer passage ranked 7th or 8th in 3 cases and was outside the top 10 in 2. In one case the
  right page was shown, but only its footnotes passage.
- **Rewriting follow-up questions** raises "right page in the top 5" from 3/8 (as typed) to 7/8.
  This counts pages, not passages: one of the 7 got only an unhelpful passage from the right
  page.
- **On the tuning set, a threshold of 0.60 and 8 passages look better.** 8 passages became the
  default in Phase 9; the 0.60 threshold is still not applied:
  - off-topic questions reaching the model would drop from 5/8 to 1/8;
  - the right page would be kept for 37/39 instead of 34/39;
  - 8 passages would have shown the answer passage for 3 of the 4 tuning false refusals.

### top_k 8 experiment

A full answer run with 8 passages instead of 5, set for that evaluation run only. The default
was 5 when this was run; **Phase 9 made 8 the default**, based on this experiment.

| | Tuning (n=55) top 5 | Tuning top 8 | Held-out (n=10) top 5 | Held-out top 8 |
|---|---|---|---|---|
| Answerable questions wrongly refused | 2/31 | 0/31 | 1/6 | 1/6 |
| Follow-ups wrongly refused | 2/8 | 1/8 | – | – |
| Off-topic refused | 8/8 | 8/8 | 2/2 | 2/2 |
| On-topic, not in the documents, refused | 8/8 | 8/8 | 2/2 | 2/2 |
| Answers with ≥1 correct citation | 34/35 | 36/38 | 5/5 | 5/5 |
| Cited sources on expected pages | 36/42 | 39/47 | 6/6 | 6/6 |
| Mean prompt characters per answer | 6,775 | 10,247 | 7,012 | 10,913 |

- **Effect:** the 3 false refusals whose answer passage had ranked 7th–8th are now answered
  correctly. No unanswerable question was answered.
- **Side effects:**
  - one previously cited answer (sky-01) is now correct but uncited;
  - 2 more cited sources fall outside the expected pages.
- **Cost:** about 59% more passages and 51–56% more prompt text per answer.
- **Caveats:**
  - the change was proposed after tracing these same misses;
  - the held-out set cannot confirm it: its one false refusal is out of reach, and nothing
    else changed;
  - the gain rests on 3 questions.

### Reworded questions and the front-matter filter (Phase 9)

Retrieval only (no LLM calls), at threshold 0.55 and top_k 8. Full report:
[front-matter-filter.md](docs/evaluation/front-matter-filter.md).

- **Reworded questions:** the dataset has a separate set of 31 natural rewordings of the
  answerable tuning questions, avoiding the documents' own terms. One of them (rw-sky-04) is a
  question a real user typed in the app; the other 30 were written by Claude and reviewed by the
  owner. The held-out questions were not reworded or touched.
- **Front-matter filter:** a rule that recognises table-of-contents and list-of-figures passages
  (at least 5 dot leaders, and at least one per 18 words), behind the setting
  `exclude_front_matter`.

| | Tuning, filter off | Tuning, on | Reworded, off | Reworded, on | Held-out, off | Held-out, on |
|---|---|---|---|---|---|---|
| Right page in the top 8 (hit@8) | 37/39 | 37/39 | 22/31 | 22/31 | 5/6 | 5/6 |
| Right page in the top 5 (hit@5) | 34/39 | 34/39 | 21/31 | 22/31 | 5/6 | 5/6 |
| Right page among the passages kept | 37/39 | 37/39 | 22/31 | 22/31 | 5/6 | 5/6 |
| Kept passages that are front matter | 11/312 | 0/312 | 7/248 | 0/248 | 0/48 | 0/48 |
| Questions with a front-matter passage | 9/39 | 0/39 | 5/31 | 0/31 | 0/6 | 0/6 |

- **Rewording costs more than anything the filter changes.** The right page reaches the top 8
  for **95% (37/39)** of tuning questions as worded in the dataset, but only **71% (22/31)** when
  the same questions are reworded naturally. The dataset's wording, written while reading the
  pages, flatters retrieval; 71% is the more honest figure for real students. The user's own
  Skylab question (rw-sky-04) is still missed: its answer passage isn't in the top 60.
- **The filter removes only front matter.** It flags 20 chunks, all on the Skylab report's
  contents and list pages (13–23), none on a page any question expects. It frees 11 of 312 kept
  passages on the tuning set without losing any expected page.
- **Decision: the filter stays off by default.** The rule fixed before measuring required an
  improvement in "right page kept" or hit@8 on a tuning set, and neither changed (only hit@5 on
  the reworded set, 21 → 22). Where the filter helped, the answer page was already kept at top_k
  8; where retrieval failed, the answer page ranked too low for freed slots to reach it. The
  setting can be turned on in `.env` (`EXCLUDE_FRONT_MATTER=true`). An answer evaluation, which
  costs Gemini calls, could show whether the model answers better with less noise.
- **Run-to-run variation:** two runs on the same code matched everywhere except the best-score
  range of the 2 held-out off-topic questions (0.467–0.501 vs 0.501–0.504). Chroma's search is
  approximate (HNSW) and the index is rebuilt for each run, so low-scoring questions with no
  close match can get slightly different nearest neighbours. No count in the table changed.

**Caveats**
- The faithfulness judge is the same model family as the answerer, so the faithfulness score is
  biased upwards.
- Settings were chosen on the tuning set, so tuning-set numbers are optimistic.
- The 10 held-out questions were drafted with AI help and reviewed by the owner.
- The 2 held-out off-topic questions cannot confirm the threshold: both score about 0.50, so
  they are refused at both 0.55 and 0.60 and can't tell those settings apart.

## Future work

Retrieval ideas aimed at the gap shown by the reworded questions: the right page reaches the top
8 for 95% (37/39) of questions as worded in the dataset, but 71% (22/31) when reworded. Each
idea would need the same before/after measurement, on the tuning, reworded and held-out sets
separately, before becoming a default.

- **Keyword or hybrid search:** combine the embedding search with keyword matching (e.g. BM25),
  so exact terms like "drinking water" or "OWS" count even when the overall meaning is close to
  many other passages.
- **A re-ranker:** score the top 20–50 candidates again with a cross-encoder model that reads the
  question and the passage together. More accurate than embeddings alone, but slower, and a new
  dependency.
- **Smaller or section-aware chunks:** 1800-character chunks can mix a section heading, a figure
  and several topics, which blurs their embedding. Splitting at section boundaries or using
  smaller chunks could help; the Phase 7 chunk-size sweep was within noise at n = 39.

## Hardening (Phase 9)

What a user now sees when something goes wrong (details in
[the Phase 9 notes](docs/phase-notes/phase-9-hardening.md)):

- **No API key:** an amber banner explains how to add `GEMINI_API_KEY` to `backend/.env` and
  restart the backend. Uploading and browsing still work.
- **Backend stopped:** a red banner, re-checked every 30 s, when the tab regains focus, or with
  "Check now".
- **Daily AI quota used up:** a clear "try again tomorrow" message, with no pointless Retry.
  A short per-minute limit still shows a countdown.
- **Too-large PDF:** refused at once, before any upload (limit 50 MB).
- **Empty, password-protected or damaged PDF:** a clear message instead of a server error.
- **After an upload:** "Indexed notes.pdf: text found on 12 of 20 pages", and a note when some
  pages are scanned images.
- **A very long summary:** stops starting new AI calls after 180 s and returns a partial summary,
  marked as such.
- **A document deleted in another tab:** the document list refreshes itself and the message
  says to try again. Unexpected server errors show a friendly message, never internal details.

Two optional behaviours are off by default; turn them on in `backend/.env`, then restart the
backend:

| Setting | Default | What it does |
|---|---|---|
| `EXCLUDE_FRONT_MATTER=true` | off | Leave tables of contents and lists of figures out of answers and study tools. Measured: no gain in finding the right page, so off. |
| `STARTUP_CLEANUP=true` | off | At startup, delete leftovers of interrupted uploads (old temporary files, PDFs and chunks with no document). A report-only run on real data found nothing to delete. |

## Sample documents and licences

The PDFs used for the evaluation and the manual checks are **not in this repository** (they
are git-ignored). StudyMate works with any PDFs you upload yourself.

| Document | Used for | Source | Licence |
|---|---|---|---|
| MSFC Skylab Crew Systems Mission Evaluation (NASA TM X-64825), `19740024203.pdf` | Evaluation | NASA technical report | NASA in-house report; I am not redistributing the PDF |
| Space Telescope Focal Plane Camera Final Report (NASA-CR-150117), `19770007900.pdf` | Evaluation | NASA Technical Reports Server (ntrs.nasa.gov), document 19770007900, NASA-CR-150117, contractor report, April 1976 | Public Use Permitted (as stated on the NTRS record); I am not redistributing the PDF |
| IPCC AR6 Synthesis Report, Summary for Policymakers, `IPCC_AR6_SYR_SPM.pdf` | Evaluation | ipcc.ch | IPCC permits short attributed extracts; the PDF is not in this repository |
| `sample1.pdf` | Manual checks | `<TO FILL IN>` | `<TO FILL IN>` |

## Tech stack

- **Backend:** Python, FastAPI, SQLite, ChromaDB, sentence-transformers, the Gemini API.
- **Frontend:** React 19, TypeScript 7, Vite 8, Tailwind CSS 4.
- **Tests:** pytest for the backend; Vitest and Testing Library for the frontend.

## Run the backend

For development: the backend and the frontend run separately, in two PowerShell windows, with
automatic reload. To just use the app, see [Quick start (Windows)](#quick-start-windows).

```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }   # never overwrites an existing .env
uvicorn app.main:app --reload
```

Then open http://127.0.0.1:8000/docs

## Run the frontend

Needs Node.js 22.12 or newer (developed with Node 24). Keep the backend running in one
PowerShell window, then in a second one:

```powershell
cd frontend
npm install
npm run dev
```

Then open http://localhost:5173. The Vite dev server forwards every `/api/...` request to the
backend at http://127.0.0.1:8000 (removing the `/api` prefix), so the backend needs no CORS
setup.

Other scripts, run from `frontend/`:

| Command | What it does |
|---|---|
| `npm test` | Runs the frontend tests (Vitest; the API is mocked, so no backend or API key is needed) |
| `npm run typecheck` | Type-checks the code (`tsc --noEmit`) |
| `npm run build` | Type-checks, then builds the production files into `frontend/dist/` |