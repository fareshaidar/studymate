# Phase 8 request: frontend (React + Vite + TypeScript + Tailwind)

Approved plan. Follow CLAUDE.md: small steps, tests, full suites after each step, commit named
files only, and never start the next phase without the owner's OK.

## Goal
A browser UI in a new `frontend/` folder that uses the existing backend:
- upload and manage PDFs;
- choose which documents to search;
- chat with cited answers and conversation memory;
- use the study tools (summary, quiz, flashcards).

Constraints: no backend setting default changes, and no test calls Gemini.

## Decisions (owner)
1. **Node.js:** installed by the owner. Claude Code is restarted so `node`/`npm` are on PATH.
2. **Dev connection:** a Vite dev proxy, not CORS. The proxy strips the `/api` prefix
   (`/api/documents` → `http://127.0.0.1:8000/documents`), because the backend routes have no
   `/api` prefix. A test covers the rewrite.
3. **PDF at the cited page:** add `GET /documents/{id}/file` with pytest tests:
   - 200 with `application/pdf`;
   - 404 for an unknown id;
   - 404 if the row exists but the file is missing;
   - no path traversal: the path is built from the stored id only.

   A citation's "Open PDF at page n" opens `/api/documents/{id}/file#page=n` in a new tab. Browsers'
   built-in PDF viewers honour `#page=`.
4. **Document selection** is stored per conversation in `localStorage`.
5. **Tests:** Vitest + Testing Library with a mocked API, plus a manual checklist. No browser
   end-to-end tool.
6. **Out of scope:** streaming answers, indexing progress, dark mode, renaming conversations.

## Backend endpoints used (all exist except the new file endpoint)

| Endpoint | Used for | Notes |
|---|---|---|
| `GET /health` | "backend offline" banner | `{"status":"ok"}` |
| `POST /documents` (multipart `file`) | upload | 201 `{id, filename, page_count, chunk_count, created_at}`; 400 not a PDF, 413 over 50 MB, 422 no text |
| `GET /documents` | document list | newest first |
| `DELETE /documents/{id}` | delete | 204 / 404 |
| `GET /documents/{id}/file` (new) | open the PDF at a cited page | 200 PDF / 404 |
| `POST /chat` `{question, document_ids?, conversation_id?}` | ask | `{answer, found, reason, sources[{n, document_id, filename, page, snippet, score, cited}], conversation_id, rewritten_question}`; `reason` is ok, no_relevant_chunks or model_declined |
| `GET /conversations` | conversation list | `{id, title, created_at}`, newest first |
| `GET /conversations/{id}` | reopen a chat | messages with `role, content, sources, reason` |
| `DELETE /conversations/{id}` | delete a chat | 204 / 404 |
| `POST /study/summary` `{document_ids, topic?}` | summary | `found, message, summary, truncated, llm_calls, pages[]` |
| `POST /study/quiz` `{document_ids, topic?, num_questions 1–10}` | quiz | options already shuffled server-side, `correct_index`, `source` |
| `POST /study/flashcards` `{document_ids, topic?, num_cards 1–20}` | flashcards | `front, back, source` |

**Errors:** most errors return `{"detail": "<friendly text>"}`:
- 4xx errors;
- 503 with `Retry-After` when rate-limited;
- 502 for a provider failure;
- 500 when no API key is set.

FastAPI's 422 validation errors have `detail` as a list instead. The client normalises both into one
`ApiError {status, message, retryAfter?}`.

**Known limits:**
- **Upload:** `POST /documents` indexes synchronously (about a minute for a 400-page PDF). The UI
  shows the bytes uploaded (via `XMLHttpRequest`, since `fetch` can't report upload progress), then
  "Indexing…" until the response arrives.
- **Chat:** `/chat` is not streaming, so the UI shows a loading state.

## Screens and components
One page, no router: a left sidebar and a main area with two tabs, **Chat** and **Study**.

- **Sidebar**
  - `DocumentPanel`:
    - `UploadDropzone`: drag and drop or pick a file; progress, then indexing state; inline errors
      for 400, 413 and 422.
    - `DocumentList`: filename, pages, a checkbox per document for the search scope (none ticked =
      all documents), delete with a confirm step.
  - `ConversationList`: "New chat", open, delete with a confirm step.
  - `BackendStatus`: a banner when `/health` fails.
- **Chat** (`ChatView`)
  - `MessageList`: the history comes from `GET /conversations/{id}`.
  - `AnswerMessage`: each `[n]` in the answer is a `CitationChip` button. Clicking it opens a card
    with the document name, page and snippet, and "Open PDF at page n".
  - `SourceList`: the cited sources, with uncited retrieved passages folded away.
  - `NotFoundNotice`: shown when `found` is false. It reads "Not found in your material", gives the
    reason in plain words, and suggests rephrasing or selecting more documents.
  - A "searched as: …" line when `rewritten_question` is set.
  - `MessageInput`: disabled while waiting, with a typing indicator. `ErrorNotice` offers a retry,
    and on a 503 says "busy, try again in N s".
- **Study** (`StudyView`, which uses the same document selection)
  - `SummaryPanel`: optional topic; shows a partial-summary warning when `truncated`, and the pages
    used.
  - `QuizPanel`: number of questions and optional topic. Answer a question, then reveal the correct
    option, the explanation and the source.
  - `FlashcardsPanel`: number of cards and optional topic. Cards flip and show their source.
  - `found: false` uses the `NotFoundNotice` style with the backend's `message`.
- **Empty states:** with no documents, prompt for an upload; with no conversations, offer to start
  one.

## Folder structure
```
frontend/
  package.json, package-lock.json, vite.config.ts (proxy + Vitest), tsconfig*.json, index.html
  src/
    main.tsx, App.tsx, index.css (Tailwind)
    api/         types.ts, client.ts, documents.ts, upload.ts, chat.ts, conversations.ts, study.ts
    lib/         citations.ts, selection.ts
    components/  documents/, chat/, conversations/, study/, common/
    *.test.ts(x) next to the code they test
```

## Libraries (few)
- **The chosen stack:** `react`, `react-dom`, `typescript`, `vite`, `@vitejs/plugin-react`, and
  `tailwindcss` with `@tailwindcss/vite`.
- **Tests only (dev):** `vitest`, `@testing-library/react`, `@testing-library/user-event`,
  `@testing-library/jest-dom`, `jsdom`.
- **Not adding:** a router, axios or a data-fetching library, a component library, a state manager,
  a Markdown renderer, or browser end-to-end tools.

## Running on Windows (two PowerShell windows)
```powershell
cd backend; .\.venv\Scripts\Activate.ps1; uvicorn app.main:app --reload   # 1: backend
cd frontend; npm install; npm run dev                                      # 2: http://localhost:5173
```
Scripts: `npm run dev`, `npm test`, `npm run typecheck` (`tsc --noEmit`), `npm run build`. The root
`.gitignore` already excludes `node_modules/` and `dist/`.

## Steps (riskiest first)
Each step: explain it, implement it, run `npm test` and `npm run typecheck` (plus `pytest` when the
backend changes), then commit the named files only.

1. **The connection:**
   - scaffold Vite + React + TypeScript + Tailwind;
   - the dev proxy with the `/api` rewrite (tested);
   - `api/client.ts`: `ApiError` normalisation and `Retry-After`;
   - `api/upload.ts`: XHR with progress;
   - a temporary smoke screen: backend status, upload, document list.

   Tests use a mocked XHR and fetch. Manual check: upload a long PDF through the proxy and confirm the
   minute-long request doesn't time out. Each installed package is explained first.
2. **Backend:** `GET /documents/{id}/file`, with pytest tests. No setting default changes.
3. **Documents panel:** progress and indexing state, list, delete with confirm, selection per
   conversation.
4. **Citations:**
   - `lib/citations.ts`: parse `[n]`, ignore numbers that have no source, keep the text intact;
   - `AnswerMessage`, `CitationChip` with "Open PDF at page n", `SourceList`, `NotFoundNotice`.
5. **Chat flow:** send, loading, the conversation id carried to follow-ups, "searched as", and the
   error states (503 with `Retry-After`, 502, 500, 404).
6. **Conversations:** list, open (render the stored messages and sources), new, delete.
7. **Study tools:** summary, quiz, flashcards, with not-found and error states.
8. **Polish:** empty states, the offline banner, keyboard and screen-reader basics, narrow screens.
9. **Wrap-up:** README run instructions, `docs/phase-notes/phase-8-frontend.md` with 5 interview
   Q&As, and the CLAUDE.md "Done so far".

## Verification
- **After every step:** `npm test`, `npm run typecheck`, and backend `pytest -q`, which stays green
  (324 tests plus the new endpoint tests).
- **At the end, a manual checklist with both servers running:**
  - upload: progress, indexing, errors;
  - select documents, ask, click citations, open the PDF at the cited page;
  - the not-found case;
  - a follow-up in the same conversation;
  - reopen and delete a conversation;
  - summary, quiz and flashcards;
  - stop the backend and check the offline banner.
