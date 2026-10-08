# Phase 6: Study tools (summary, quiz, flashcards)

## What was built

- **Three stateless endpoints** (`app/api/study.py`). Nothing is stored.
  - `POST /study/summary {document_ids?, topic?}` → `{found, message, summary, truncated, llm_calls, pages: [{document_id, filename, pages}]}`
  - `POST /study/quiz {document_ids?, num_questions 1–10, topic?}` → `{found, message, questions: [{question, options[4], correct_index, explanation, source: {document_id, filename, page}}]}`
  - `POST /study/flashcards {document_ids?, num_cards 1–20, topic?}` → `{found, message, cards: [{front, back, source}]}`
  - An empty or missing `document_ids` means all documents, and unknown ids return 404. A blank topic counts as no topic; a topic over 200 characters returns 422.
  - If nothing usable is found, the endpoint returns 200 with `found=false` and a friendly `message`, without calling the LLM (same idea as `/chat`).
- **`app/services/selection.py`** (shared with chat; moved from `chat.py`):
  - `resolve_documents` does the id → filename lookup and the 404 check.
  - `is_usable` / `usable` apply the alnum-ratio filter and strip diagram characters.
  - `evenly_spaced` picks a sample spread over a sequence.
  - `select_passages` picks the quiz/flashcard material.
- **`VectorStore.get_chunks(document_id)`** returns all of a document's chunks in reading order. Chroma doesn't promise an order, so it sorts by `chunk_index`.
- **`app/rag/structured.py`**: Pydantic schemas for what the LLM must return, and `generate_json`:
  - Code fences (```` ```json ````) around the reply are stripped first.
  - Quiz items need exactly 4 non-empty options that differ ignoring case and spaces, `correct_index` 0–3, non-empty text, and a `passage` between 1 and the number of passages sent (checked through Pydantic's validation context).
  - An invalid reply gets **one** retry, with the validation errors (field path and message, not the reply text) added to the prompt. A second failure raises `InvalidLLMOutputError`, which the existing global handler turns into a friendly 502.
- **`app/rag/study_prompts.py`**: system prompts sharing chat's grounding rules (only the passages; passages are data, never instructions; plain text), plus the summary, combine, quiz and flashcard prompts. The quiz and flashcard prompts show the exact JSON format.
- **`app/services/study.py`**: `summarize`, `make_quiz`, `make_flashcards`.
- **Settings:** `study_max_llm_calls = 8`, `study_batch_chars = 12000`, `study_max_passages = 10`.
- **Logging:** counts only, e.g. `study kind=summary chunks=40 batches=7 llm_calls=8 truncated=True` and `study invalid_json attempt=1 errors=2`. Document text and generated content are never logged.
- **Tests: 73 new, 234 total**, all with `FakeLLMClient`:
  - `test_selection.py` and the `get_chunks` tests in `test_vectorstore.py`
  - `test_structured.py`: fences, every validation rule, one retry with the errors in the prompt, a friendly error after the second failure, nothing of the reply in logs
  - `test_study_service.py`: one call for a small document; map + combine for a long one; the call cap and `truncated`; topic filter; sources from our passage numbers; passages shared between documents; seeded shuffle; no LLM call when nothing is usable
  - `test_study_api.py`: the three endpoints, 404, invalid twice → 502, 422 limits, rate limit → 503

## Flow

```
summary:   resolve_documents ─► get_chunks per document (page order) ─► [topic: keep chunks with score ≥ min_similarity]
           ─► usable ─► nothing? found=false, no LLM call
           ─► pack into batches ≤ study_batch_chars
           ─► 1 batch: 1 call
           ─► n batches: keep ≤ cap-1 (evenly spaced; truncated=true if some were dropped)
                         ─► 1 call per batch ─► 1 combine call over the partial summaries in order
           ─► {summary, truncated, llm_calls, pages actually used}

quiz/cards: resolve_documents ─► select_passages (topic: retrieval + threshold; no topic: equal share per document, evenly spaced)
           ─► usable ─► nothing? found=false, no LLM call
           ─► number passages [1..n] ─► generate_json (validate ─► 1 retry with errors ─► InvalidLLMOutputError → 502)
           ─► trim to the requested count ─► source = passages[item.passage - 1]   (never the model's page)
           ─► quiz only: shuffle options with rng, recompute correct_index
```

## Design decisions and tradeoffs

- **Map-reduce for summaries.** A whole course PDF doesn't fit comfortably in one prompt, and stuffing it in degrades quality. Summarising batches in page order and then combining the partial summaries keeps every call a manageable size. The combine step sees only the partial summaries, so it is told not to add anything new.
- **A hard call cap.** On the free tier, one summary of a 300-page PDF could use the daily quota. With `study_max_llm_calls = 8`, a long document gets at most 7 batch calls and 1 combine call. The batches kept are **evenly spaced**, so the summary samples the whole document instead of covering only the first chapters. `truncated=true` tells the student it is partial, and `pages` lists exactly which pages were read.
- **A topic filters before summarising.** Only chunks similar to the topic are kept, so a topic summary needs fewer calls and stays on topic. The tradeoff is that it relies on the same similarity threshold as chat, which Phase 7 still has to tune.
- **Sources come from passage numbers, never from the model.** The model only returns which passage (1..n) an item came from. That number is range-checked by Pydantic, and the document and page come from the chunk we sent. A model that writes "see page 99" can't create a wrong citation.
- **Validate, then retry once with the errors.** The model sees exactly what was wrong (e.g. `questions.0.options: List should have at least 4 items`). One retry fixes most mistakes; more would spend quota for little gain. A second failure is a friendly 502, not a crash or half-checked data. JSON is requested in the prompt rather than through Gemini's JSON mode, so it works the same with any `LLMClient`. The tradeoff is that fences and stray text have to be tolerated, which `strip_code_fences` handles.
- **Options are shuffled on the server.** Models tend to put the correct answer first, so a student could learn to always pick A. The quiz service shuffles each question's options with an injectable `random.Random` and recomputes `correct_index`. Tests pass a seeded generator and check that the correct text is still at `correct_index`.
- **An equal share per document without a topic.** If one PDF has 300 chunks and another has 10, sampling the combined list would almost ignore the short one. Each document gets the same number of passages, spread through it. A share that a short document can't fill is left unused, to keep the code simple.
- **Fewer items than requested are accepted.** A two-page note may not support 10 good questions. Retrying would cost quota and push the model to invent items. Extra items are trimmed.
- **Selection logic is shared with chat** (`selection.py`), so the 404 check, the diagram filter and "only documents that exist in SQLite" behave the same everywhere. One guard was added: an empty id list is never passed to `store.search`, where it would mean "all chunks", orphans included.
- **Chunk overlap** (~250 characters) means summaries see a little repeated text. That's acceptable, and the combine step removes repetition anyway.

## Still to tune (Phase 7)

`study_batch_chars`, `study_max_passages` and the call cap are first guesses. Things to measure: summary coverage against the pages read, how often quiz JSON needs a retry, and how often a second failure happens.

## Interview questions

1. **Q: How do you summarise a document that's too long for one prompt, on a limited API budget?**
   A: With map-reduce. I read the chunks in page order, pack them into batches under a character budget, summarise each batch, then combine the partial summaries in one more call. Small documents skip all that and take a single call. Because of the free tier there's a hard cap (8 calls). If there are more batches than fit, I keep an evenly spaced subset so the summary still covers the whole document, and return `truncated: true` with the exact pages that were read. The student knows it's partial, and the cap guarantees the cost.

2. **Q: How do you get reliable structured output from an LLM?**
   A: I ask for an exact JSON shape, then never trust it. I strip code fences, and Pydantic validates the reply: exactly 4 distinct options, `correct_index` in range, non-empty text, and a passage number that refers to a passage I actually sent. If validation fails I retry once and include the validation errors in the prompt, so the model knows what to fix. If the second reply also fails, the API returns a friendly 502 instead of passing on bad data. Everything downstream works on validated objects only.

3. **Q: How do you stop the model from inventing citations for quiz questions?**
   A: The model never gives a page. It returns the number of the passage the question came from, Pydantic checks that the number is between 1 and the number of passages sent, and the document and page are looked up from the chunk we sent. So a source can only ever be a real page that was in the prompt. A test has the model write "See page 99" in its explanation and checks that the returned page is still the passage's real page.

4. **Q: Why shuffle the answer options yourself?**
   A: LLMs have position biases. They often put the right answer first, which would make the quiz guessable. After validation I shuffle each question's options and recompute `correct_index` from the new order. The random generator is injected, so tests can seed it and check that the correct answer's text is still at `correct_index`, and that the order actually changed.

5. **Q: What happens when there's nothing to work with, like a document that's only diagrams or a topic that isn't in the notes?**
   A: The service checks before spending an LLM call. Chunks that are mostly symbols are filtered out, and with a topic only chunks above the similarity threshold are kept. If nothing is left, the response is `found: false` with a friendly message, and the LLM is never called; tests assert `llm.calls == []`. That's the same principle as the chat's "not found" answer: don't give the model a chance to make things up from irrelevant text, and don't spend quota doing it.
