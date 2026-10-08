# StudyMate

A RAG-based study assistant. Upload your lecture notes and PDFs, ask questions,
and get answers with citations to the exact document and page. It also
generates summaries, quizzes, and flashcards from your material.

> Status: the backend is done (Phases 0–7: ingestion, cited chat, conversations, study tools,
> evaluation). Next: Phase 8, the React frontend.

## Features

- PDF upload and indexing, with answers citing the exact document and page
- A "not in your documents" answer when the material doesn't cover the question
- Conversations with follow-up questions
- Summaries, quizzes and flashcards from your documents
- An evaluation suite for retrieval and answer quality (see [Evaluation](#evaluation))

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

**Caveats**
- The faithfulness judge is the same model family as the answerer, so the faithfulness score is
  biased upwards.
- Settings were chosen on the tuning set, so tuning-set numbers are optimistic.
- The 10 held-out questions were drafted with AI help and reviewed by the owner.
- The 2 held-out off-topic questions cannot confirm the threshold: both score about 0.50, so
  they are refused at both 0.55 and 0.60 and can't tell those settings apart.

## Tech stack

Python, FastAPI, ChromaDB, sentence-transformers, Gemini API, React.

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