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
Phases 0 to 4 are complete: ingestion API (upload/list/delete), LLM client
with retries and an optional fallback model, POST /chat with a similarity
threshold, citation validation, a reason field, the orphan-chunk fix and the
diagram-noise filter. Notes are in docs/phase-notes/.
Next: Phase 5 (conversation memory).

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