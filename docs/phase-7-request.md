# Phase 7 request: evaluation

Plan Phase 7 and wait for my OK. Do not write code yet.

## Goal
Measure how well retrieval and answering work, so the first-guess settings
(min_similarity 0.55, retrieval_top_k 5, min_alnum_ratio 0.5, the rewrite
prompt) can be tuned with evidence, and so the README can show real numbers.

## Dataset (evaluation/datasets/)
- A JSON file of questions about sample documents kept in the repo. Use only
  documents that are fine to publish (public domain or my own).
- Each item: id, question, type (answerable / unanswerable_off_topic /
  unanswerable_on_topic / follow_up), the expected document and the expected
  page(s) for answerable ones (any page that really contains the answer
  counts), and a short reference answer. Follow-ups carry the earlier turns
  and the expected standalone question.
- Aim for about 40 to 60 questions. I will review the ground truth by hand,
  so list in the plan how it will be created and checked.

## Retrieval metrics (no LLM calls, fast, free)
- Hit rate at k, recall at k, and MRR against the expected pages.
- Score distributions for answerable versus unanswerable questions.
- A sweep of min_similarity (for example 0.45 to 0.70) reporting false
  refusals on answerable questions and false answers on unanswerable ones.
- A sweep of retrieval_top_k and, if feasible, of chunk size and overlap
  (this needs re-indexing into a temporary store, never my real data).

## Answer metrics (uses the LLM, so limited)
- Refusal accuracy on the unanswerable questions, split by off-topic and
  on-topic, using the reason field to say which layer refused.
- Citation accuracy: the cited pages versus the expected pages.
- Faithfulness: an LLM judge checks whether each claim is supported by the
  cited passages. Cap the number of calls, cache results, allow a
  `--limit N`, and say clearly in the report that the judge is the same
  family of model as the answerer, which biases the score.
- Follow-up rewrites: how often the rewrite matches the expected standalone
  question in meaning (judge) and how often it falls back.

## Tooling
- Scripts in evaluation/: run_retrieval_eval.py, run_answer_eval.py,
  metrics.py. They call the same services as the API.
- A `--no-llm` mode and a `--fake-llm` mode for tests and quick runs.
- Output: results/*.json and a markdown report with tables, plus a small
  chart if easy (matplotlib only if a new dependency is justified).
- Evaluation must use a temporary vector store and database, never
  backend/data. Never open .env.
- Handle Gemini 503 and 429 gracefully: retry later, record the failure, do
  not count it as a wrong answer.

## Tests
- metrics.py is covered by unit tests with tiny hand-made examples.
- The runners are tested end to end with the fake LLM and a tiny dataset.

## Out of scope
New features, hybrid search or a reranker (those come after we have
baseline numbers), the frontend.

Follow CLAUDE.md.