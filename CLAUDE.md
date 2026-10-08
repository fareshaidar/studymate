# StudyMate: instructions for Claude Code

## Project
StudyMate is a RAG study assistant, built as a portfolio project by a CS (AI)
student who must be able to explain every component in an interview.
Environment: Windows, PowerShell, Python 3.11, venv at backend/.venv.

## Stack (do not change without asking)
- FastAPI, Pydantic, pydantic-settings, SQLAlchemy + SQLite
- Embeddings: sentence-transformers, BAAI/bge-small-en-v1.5 (local)
- Vector store: ChromaDB, wrapped in app/rag/vectorstore.py
- LLM: Gemini (google-genai) behind the LLMClient abstraction in app/llm/
- PDF parsing: PyMuPDF. Chunks never cross page boundaries.
- Frontend later: React + Vite + TypeScript + Tailwind

## Done so far
Phases 0 to 9 are complete: ingestion API (upload/list/delete), LLM client
with retries and an optional fallback model, POST /chat with a similarity
threshold, citation validation, a reason field, the orphan-chunk fix and the
diagram-noise filter; conversations (stored messages, follow-up rewriting with
fallback, history in the prompt, /conversations endpoints); study tools
(/study/summary map-reduce with an LLM call cap, /study/quiz and
/study/flashcards with Pydantic-validated JSON, one retry, sources from
passage numbers, server-side option shuffle); evaluation (backend/evaluation/:
65-question dataset, 55 tuning + 10 owner-written held-out, never used to choose
settings; retrieval and answer runners on a temporary index, LLM judge, reply
cache and call cap; baseline reports in docs/evaluation/); the frontend (frontend/:
React + Vite + TypeScript + Tailwind, a Vite dev proxy that strips /api instead of
CORS, GET /documents/{id}/file for "Open PDF at page n", per-conversation document
selection in localStorage, chat, conversations, study tools; Vitest + Testing
Library tests with a mocked API; run with npm run dev, npm test, npm run typecheck);
hardening (Phase 9: front-matter rule and 31 reworded tuning questions measured
retrieval-only; missing-key banner and llm_configured/max_upload_mb in /health;
daily quota as 429; early 413 from Content-Length and batched Chroma adds; 422s for
empty, password-protected and damaged PDFs and text_page_count on upload; catch-all
JSON 500 and error codes; startup cleanup; summary time budget; input limits;
SQLite foreign keys, WAL and busy timeout; recap in docs/phase-notes/phase-9-hardening.md).
retrieval_top_k is 8 since Phase 9 (was 5). The front-matter filter
(exclude_front_matter) was measured in Phase 9 and stays off by my decision: no
gain in expected page kept or hit@8 (37/39 tuning, 22/31 reworded, 5/6 held-out).
min_similarity 0.60 still awaits my decision. The dataset's "reworded" section (31
rewordings of answerable tuning items; rw-sky-04 is my own wording) is tuning-side
only; never reword or use the held-out items for choosing settings.
startup_cleanup stays False until I say otherwise (report-only run found nothing).
study_max_seconds is 180. Never commit backend/data/ (it holds studymate.db, its
-wal/-shm files and my backup studymate.db.bak).
Evaluation PDFs are git-ignored; never commit them or backend/evaluation/results/.
Notes are in docs/phase-notes/.
Next: Phase 10 (packaging).

## Roadmap (one phase at a time, never start the next without my OK)
5 Conversation, 6 Study tools, 7 Evaluation, 8 Frontend, 9 Hardening,
10 Packaging.

## How to work with me
1. Before each major step, explain in 2-4 sentences what you will build and
   why, then wait for my OK.
2. Small steps, with tests. Run the full test suite after each step.
3. Simple, readable code with type hints and short docstrings. Comment the
   "why". I am a student: avoid clever tricks.
4. At the end of each phase write a recap in docs/phase-notes/: what was
   built, how the pieces connect, design tradeoffs, and 5 interview
   questions with answers.
5. Commit named files only, after the tests pass.

## Rules
- Never open, read or print .env.
- Never commit .env, .venv, data/ or try_*.py. Never use git add . or -A.
- Tests never call the real Gemini API; use FakeLLMClient.
- Do not add dependencies without explaining why.
- If something fails, explain the cause before fixing it.