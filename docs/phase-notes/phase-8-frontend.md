# Phase 8: Frontend

A browser UI in `frontend/` (React 19, Vite 8, TypeScript 7, Tailwind 4) for the existing backend:
upload and manage PDFs, choose which ones to search, chat with cited answers and conversation
memory, and use the study tools. The plan is in [phase-8-request.md](../phase-8-request.md).

## What was built

| Step | Commit | What |
|---|---|---|
| 1 | `71325d8` | Scaffold, the `/api` dev proxy, `ApiError` normalisation, upload with progress (XHR) |
| 2 | `6e7059c` | Backend: `GET /documents/{id}/file`, served inline, with path-traversal tests |
| 3 | `c0d1175` | Documents panel: drag-and-drop upload, indexing state, delete with confirm, per-conversation selection |
| 4 | `2481dfa` | Citation parsing, citation chips and cards with "Open PDF at page n", source list, not-found notice |
| 5 | `19036b6` | Chat flow: thinking state, follow-ups, "Searched as", error states with Retry and the 503 countdown |
| 6 | `f11745a` | Conversations: list, reopen from stored messages, new chat, delete; "(document deleted)" sources |
| 7 | `fc83009` | Study tab: summary, quiz, flashcards, with not-found and error states |
| 8 | `9f6a896` | Polish: empty states, re-checking offline banner, keyboard and screen-reader basics, narrow screens |

- **Step 1, the connection.** The riskiest part first: the browser reaches the backend through
  the Vite proxy, every failure becomes one `ApiError {status, message, retryAfter?}`, and a
  minute-long upload doesn't time out.
- **Step 2, the PDF endpoint.** The only backend change. The path is built from the stored id of
  an existing row, never from the URL, and the file is served `inline` so the browser's viewer
  can honour `#page=n`.
- **Step 3, documents.** The ticked documents are saved per conversation in `localStorage`. Ids of
  deleted documents are hidden, and blocked or corrupt storage falls back to "search all".
- **Step 4, citations.** `parseAnswer` splits an answer into text and `[n]` segments. A number with
  no source stays as plain text, and no character is lost.
- **Step 5, chat.** A failed request saves nothing on the backend, so the UI takes the question
  back out of the list and puts it in the input box. Retry sends it again.
- **Step 6, conversations.** A reopened chat is a fresh `ChatView`. A late answer from a chat the
  user has left is ignored.
- **Step 7, study tools.** A shared `StudyForm` and `useRequest` hook. The quiz locks each answer
  once checked and shows a score; flashcards flip one at a time.
- **Step 8, polish.** Focus management, ARIA tabs, an `aria-live` announcement, a `:focus-visible`
  outline, reduced-motion scrolling, and a sidebar that collapses below 768 px.

## How the pieces connect

```
Browser ── /api/... ──> Vite dev server (5173) ── strips /api ──> FastAPI (8000)
           (same origin, so no CORS)                           /documents, /chat, /conversations, /study
```

- **`src/api/`:** one function per endpoint. They all go through `request()` in `client.ts`, or
  through the XHR in `upload.ts`. Both turn every failure into an `ApiError`:
  - a string `detail` is used as it is;
  - FastAPI's 422 list becomes one sentence;
  - `Retry-After` is read on a 503;
  - no response at all becomes status 0.

  Components only ever handle that one error type.
- **`App.tsx` holds what several parts need:**
  - the document and conversation lists;
  - the current conversation id;
  - the selection, through `useSelection(conversationId ?? "new")`;
  - the active tab, and on narrow screens whether the sidebar is open.
- **Each panel holds its own state:** `ChatView` its messages, draft, pending request and error;
  each study panel its result through `useRequest`.
- **`key` gives a fresh chat:** `App` changes `ChatView`'s `key` for a new or reopened chat. React
  then creates a new component with empty state, so no reset code is needed.
- **The first answer starts a conversation:** `ChatView` reports the new id, and `App` moves the
  ticks from `"new"` to that id and refreshes the conversation list.
- **Reused components:** `ErrorNotice`, `NotFoundNotice`, `DeleteWithConfirm` and `Tabs` in
  `components/common/` are used by chat, study and both sidebar lists.

## Design tradeoffs

- **Dev proxy, not CORS.** The browser only talks to the Vite server, so the backend needs no CORS
  configuration. In production, a reverse proxy or FastAPI serving the built files would play
  the same role; that is Phase 10 (packaging).
- **XHR for upload.** `fetch` can't report upload progress. `xhr.upload.onload` marks the moment
  every byte has been sent, after which the UI shows "Indexing…" until the response arrives,
  because indexing is synchronous on the backend.
- **No router, state library or data-fetching library.** One page and a handful of requests.
  `useState`, one custom hook and props are enough, and every part can be explained.
- **Selection per conversation in `localStorage`.** It survives a reload without a backend
  change. It is per browser, though, and a new chat starts with nothing ticked.
- **Hidden tabs stay mounted.** Unmounting the Chat tab would drop an answer still loading, and
  unmounting Study would lose a quiz in progress. The cost is that both trees stay in memory,
  which is small here.
- **Stale-answer guard.** A `showing` ref is cleared when `ChatView` unmounts, so an answer that
  arrives after the user opened another chat can't attach its conversation id to that chat. A
  request counter does the same for conversation opens.
- **`found` derived from `reason`.** The backend stores `reason` but not `found` or the rewritten
  question. Reopened answers use the same rule as the backend (found means reason `ok`), and
  they show no "Searched as" line.
- **Inline delete confirm, not `window.confirm`.** It can be styled, reached by keyboard and
  tested, and focus moves to the confirm button and back.
- **The browser's own form check for counts.** `min` and `max` on the number inputs make the
  browser block, for example, 50 quiz questions with its own message. An empty field falls back
  to the default.
- **Plain text, not Markdown.** Answers render with `white-space: pre-wrap` and React's normal
  escaping, so model output can never inject HTML.

## Testing

- **159 frontend tests in 28 files** (Vitest, Testing Library, jsdom). The API is mocked with a
  stubbed `fetch` or XHR, or with `vi.mock` of an `api/` module. No test calls Gemini.
- **What they cover:**
  - the proxy rewrite and error normalisation;
  - upload progress;
  - citation parsing;
  - selection storage, including blocked storage;
  - every component's states;
  - focus handling;
  - full `App` flows against a small in-memory fake backend.
- **Backend:** 331 pytest tests, the previous 324 plus 7 for the file endpoint.
- **What jsdom can't check:** CSS (the 768 px breakpoint, `hidden` styling), real PDF viewers and
  `#page=`, and real network timing. Those are covered by the manual checklist below. There is no
  browser end-to-end tool, by decision.

## Manual checklist (both servers running, real Gemini key)

"Passed" means the owner checked it in the running app.

| Step | Check | Result |
|---|---|---|
| 1 | Long upload through the proxy (398-page PDF) does not time out | Passed |
| 2 | `/api/documents/{id}/file#page=5` opens at page 5 | Not checked separately; the step 5 "Open PDF at page n" check uses the same link |
| 3 | Upload with progress, then indexing, then listed | Passed |
| 3 | Tick a document, reload, still ticked | Passed |
| 3 | Delete with confirm | Passed |
| 3 | Dropping a `.txt` is rejected | Passed |
| 5 | Cited answer; "Open PDF at page n" opens the right page | Passed |
| 5 | Follow-up shows "Searched as" | Passed |
| 5 | Not-found, both layers (`no_relevant_chunks` and `model_declined`) | Passed |
| 5 | Stop the backend mid-chat, error shown; restart, Retry works | Passed |
| 6 | Two chats: messages, citations and ticks follow each chat | Passed |
| 6 | Reload and reopen a chat | Passed |
| 6 | Delete a chat (Cancel, then confirm) | Passed |
| 6 | Source of a deleted PDF shows "(document deleted)" | Passed |
| 7 | Summary of `sample1.pdf` | Passed |
| 7 | 3-question quiz with a checked answer | Passed |
| 7 | Topic not in the documents shows the not-found notice | Passed |
| 7 | Flashcards: flip and step through | Not yet checked |
| 7 | Switch tabs while a summary runs; the summary is still there | Not yet checked |
| 8 | Keyboard: Chat/Study tabs with the arrow keys | Passed |
| 8 | Keyboard: Enter on a citation, Escape returns focus to the chip | Not yet checked |
| 8 | Narrow window (375 px): sidebar opens, closes after opening a chat | Passed |
| 8 | Offline banner appears; "Check now" after restarting clears it and reloads lists | Not yet checked |
| 8 | Empty state with no PDFs | Not yet checked (only on an empty setup) |

## Limitations

- **Answerable questions refused at the default `top_k` 5.** Some questions are refused because
  the passage with the answer ranks just outside the top 5, so the model never sees it.
  - **Example:** the Skylab drinking-water question (`sky-04`, page 30), which the owner also hit
    in the live app. Its answer passage ranks 8th, and OCR front matter (table of contents, list
    of figures) took 2 of the 5 slots.
  - **Fixed in Phase 9 for this case:** `top_k` 8 is now the default. In the experiment it
    recovered the 3 tuning-set refusals whose answer passages ranked 7th–8th (sky-04, sky-13,
    fu-06), with no unanswerable question answered, at about 51–56% more prompt text per answer.
  - **Still refused:** fu-01 and user-06, whose answer passages rank outside the top 10. The
    held-out set couldn't confirm the change. See the
    [Phase 7 notes](phase-7-evaluation.md#top_k-8-experiment).
- **A citation card shows the opening of the passage, not the cited sentence.** The snippet is
  the first 200 characters of the passage (`SNIPPET_CHARS`), so the cited fact may be further
  into the passage and not visible in the card. "Open PDF at page n" is the way to verify it.
- **"Page n" is the PDF's page number, not the number printed on the page.** Pages are counted
  from 1 in the file, which is what `#page=n` expects. Scans with front matter or their own
  numbering can print a different number on the same page.
- **No streaming.** `/chat` and the study endpoints answer in one piece, so the UI shows a waiting
  state.
- **Indexing is synchronous.** After the upload bar reaches 100%, "Indexing…" has no progress of
  its own; a 400-page PDF takes about a minute.
- **The rewritten question isn't stored,** so a reopened chat has no "Searched as" lines.
- **Selection lives in one browser.** Another browser or a cleared storage starts with nothing
  ticked, which means all documents are searched.
- **Out of scope by decision:** dark mode, renaming conversations, and browser end-to-end tests.

## Interview questions

1. **Q: Why a Vite dev proxy instead of enabling CORS on FastAPI, and what changes in production?**
   A: With the proxy, the browser only ever talks to the Vite server, so every request is
   same-origin and the backend needs no CORS rules. Vite forwards `/api/...` to port 8000 and
   strips the prefix, because the backend routes have none. I tested the rewrite as a plain
   function and also checked GET, multipart POST and DELETE through the live proxy. In production
   the same idea holds: one origin, with either FastAPI serving the built files or a reverse
   proxy in front of both. CORS is only needed if the frontend and the API really live on
   different origins.

2. **Q: Why does the upload use `XMLHttpRequest`, and why is "Indexing…" a separate phase?**
   A: `fetch` can't report how many bytes have been sent; XHR has `upload.onprogress`. The backend
   indexes the PDF before it responds, so for a long PDF the bar reaches 100% and then nothing
   happens for a minute. `xhr.upload.onload` fires when the last byte is sent, and I use it to
   switch the message to "Indexing… this can take a minute". The request is the same; the UI
   just tells the two waits apart. Errors from both paths go through the same `buildApiError`, so
   a 413 from XHR looks exactly like one from `fetch`.

3. **Q: How do you stop a slow answer from appearing in a conversation the user has already left?**
   A: Opening another chat changes `ChatView`'s `key`, so React unmounts the old one. Its async
   `send()` is still running, though, and when the answer arrives it would call
   `onConversationStarted` and attach its id to the chat now on screen. A `showing` ref, set to
   false in the effect's cleanup, makes it ignore late results. I set it to true inside the
   effect too, because StrictMode runs effects twice in development. Opening conversations uses
   a request counter for the same reason: only the latest click's result is shown. The backend
   has still saved the late answer, so it appears when that chat is reopened.

4. **Q: How are `[n]` citations turned into buttons, and is that safe?**
   A: `parseAnswer` uses the same regex as the backend's citation check and returns segments:
   text, or a citation that points at a source object. A number with no matching source, like
   `[7]` with 5 sources or `array[0]`, stays as literal text, and a test checks that joining the
   segments rebuilds the original answer. React renders text segments as text, which it escapes,
   and citations as `<button>`s, so there is no `dangerouslySetInnerHTML` and the model can't
   inject HTML. Each chip opens a card with the snippet and an "Open PDF at page n" link built in
   one place, `pdfPageUrl`.

5. **Q: Why are the Chat and Study panels hidden instead of unmounted, and what does it cost?**
   A: In React, unmounting a component throws its state away. If switching to Study unmounted
   the chat, an answer still loading would be dropped by the stale-answer guard, and going back
   would lose a half-finished quiz. So both stay mounted and the inactive one gets the `hidden`
   attribute, which also removes it from the accessibility tree. The cost is that both trees stay
   in memory and keep their effects running. Here that's small: a few components, and no timers
   apart from the health check. With many heavy tabs, I'd lift the state up instead.
