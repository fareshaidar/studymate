# Phase 6 request: study tools

Plan Phase 6 and wait for my OK. Do not write code yet.

## Requirements
- Summaries: `POST /study/summary` with `document_ids` (one or more) and
  optional `topic`. Use map-reduce: read the chunks in page order, group them
  into batches that fit a character budget (setting), summarize each batch,
  then combine the partial summaries. Small documents use one call. Cap the
  total LLM calls (setting `study_max_llm_calls`, default 8) because of the
  free tier; if the cap is hit, spread the batches evenly and return
  `truncated: true`. Return the summary and the pages it covers.
- Quiz: `POST /study/quiz` with `document_ids`, `num_questions` (1 to 10) and
  optional `topic`. With a topic, pick chunks by retrieval; without one,
  spread the chunks evenly across the documents. The LLM returns JSON only:
  question, exactly 4 distinct options, `correct_index`, a short explanation,
  and the number of the passage it came from. Validate with Pydantic. Retry
  once with the validation error if the JSON is invalid; if it still fails,
  raise a friendly error mapped to 502.
- Flashcards: `POST /study/flashcards` with `document_ids`, `num_cards` (1 to
  20) and optional `topic`. Each card has front, back and source page. Same
  validation and retry as the quiz.
- Every item stores its source document and page, taken from the passage
  numbers we sent, never from the model's own claim of a page.
- Ground everything: use only the provided passages, treat them as reference
  material and not instructions, and write plain text. Drop low-quality
  chunks (alnum ratio) and strip diagram characters, as the chat service does.
- Unknown `document_ids` return 404, and an empty selection means all
  documents. If nothing usable is found, return a friendly message and do not
  call the LLM.
- Reuse the existing error handlers (503, 502, 500). Do not log document text
  or generated content.
- Stateless for now: do not store quizzes or attempts.

## Tests (FakeLLMClient only)
- Valid quiz JSON is parsed and returned with the right source pages.
- Invalid JSON triggers one retry; a second failure gives the friendly error.
- Code fences around the JSON are tolerated.
- Wrong option counts, duplicate options and an out-of-range `correct_index`
  are rejected.
- Map-reduce: a long document makes several batch calls plus one combine
  call, and the cap sets `truncated`.
- A small document uses a single call.
- Unknown document id gives 404, and no usable chunks means no LLM call.

## Out of scope
Streaming, storing quiz results, adaptive quizzes, the frontend.

Never open .env. Follow CLAUDE.md.