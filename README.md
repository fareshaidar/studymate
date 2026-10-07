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