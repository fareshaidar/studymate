# StudyMate

A RAG-based study assistant. Upload your lecture notes and PDFs, ask questions,
and get answers with citations to the exact document and page. It also
generates summaries, quizzes, and flashcards from your material.

> Status: Phases 0–8 are done: the backend (ingestion, cited chat, conversations, study tools,
> evaluation) and the React frontend. Next: Phase 9, hardening.

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

Baseline at the current settings (similarity threshold 0.55, top 5 passages, 1800-character
chunks). Counts are shown because n is small.

| | Tuning set | Held-out set |
|---|---|---|
| Right page ranked first (hit@1) | 24/39 | 3/6 |
| Right page in the top 5 (hit@5) | 34/39 | 5/6 |
| Answerable questions wrongly refused | 4/39 | 1/6 |
| Off-topic questions refused | 8/8 | 2/2 |
| On-topic questions not in the documents refused | 8/8 | 2/2 |
| Answers with at least one correct page citation | 34/35 | 5/5 |
| Claims supported by the cited passages (LLM judge) | 46/46 | 5/5 |

The first two rows count answerable questions plus follow-ups, and follow-ups are searched as
their intended standalone question.

**Main findings**
- **Off-topic questions** score low and are mostly stopped by the similarity threshold.
- **On-topic questions** whose answer isn't in the documents score in the same range as many
  answerable ones (0.61–0.71 vs 0.62–0.81), so no threshold separates them. The model's "not found" rule refused all 10.
- **All 5 false refusals (4 tuning, 1 held-out) were traced.** In every one, the passage
  containing the answer was not among the 5 shown to the model, so declining was correct. The
  answer passage ranked 7th or 8th in 3 cases and was outside the top 10 in 2. In one case the
  right page was shown, but only its footnotes passage.
- **Rewriting follow-up questions** raises "right page in the top 5" from 3/8 (as typed) to 7/8.
  This counts pages, not passages: one of the 7 got only an unhelpful passage from the right
  page.
- **On the tuning set, a threshold of 0.60 and 8 passages look better.** They're not applied
  yet:
  - off-topic questions reaching the model would drop from 5/8 to 1/8;
  - the right page would be kept for 37/39 instead of 34/39;
  - 8 passages would have shown the answer passage for 3 of the 4 tuning false refusals.

### top_k 8 experiment

A full answer run with 8 passages instead of 5, set for that evaluation run only. **The app
default stays at 5.**

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

**Caveats**
- The faithfulness judge is the same model family as the answerer, so the faithfulness score is
  biased upwards.
- Settings were chosen on the tuning set, so tuning-set numbers are optimistic.
- The 10 held-out questions were drafted with AI help and reviewed by the owner.
- The 2 held-out off-topic questions cannot confirm the threshold: both score about 0.50, so
  they are refused at both 0.55 and 0.60 and can't tell those settings apart.

## Tech stack

- **Backend:** Python, FastAPI, SQLite, ChromaDB, sentence-transformers, the Gemini API.
- **Frontend:** React 19, TypeScript 7, Vite 8, Tailwind CSS 4.
- **Tests:** pytest for the backend; Vitest and Testing Library for the frontend.

## Run the backend

```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

Then open http://127.0.0.1:8000/docs

## Run the frontend

Needs Node.js (developed with Node 24). Keep the backend running in one PowerShell window, then in
a second one:

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