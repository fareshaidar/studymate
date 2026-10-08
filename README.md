# StudyMate

A RAG-based study assistant. Upload your lecture notes and PDFs, ask questions,
and get answers with citations to the exact document and page. It also
generates summaries, quizzes, and flashcards from your material.

> Status: under development (Phase 0: project setup).

## Planned features

- Multi-document upload and indexing
- Grounded answers with document and page citations
- Fallback when the answer is not in the material
- Conversation memory and follow-up questions
- Summaries, quizzes, and flashcards
- Evaluation of retrieval and answer quality

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
- **Every false refusal** came from retrieval not surfacing the right page (front-matter pages
  taking slots, an answer sentence buried in an unrelated chunk); the model was right to decline
  what it was shown.
- **Rewriting follow-up questions** raises "right page in the top 5" from 3/8 (as typed) to 7/8.
- **On the tuning set, a threshold of 0.60 and 8 passages look better.** They're not applied
  yet: off-topic questions reaching the model would drop from 5/8 to 1/8, and the right page
  would be kept for 37/39 instead of 34/39.

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