# Answer evaluation

Run 2026-10-08 19:11, commit `2aafa58`.

| Setting | Value |
|---|---|
| embedding_model | BAAI/bge-small-en-v1.5 |
| min_similarity | 0.55 |
| retrieval_top_k | 5 |
| min_alnum_ratio | 0.5 |
| history_window | 6 |

Answers by the Gemini model configured in the settings. Items evaluated: 65 of 65 (round-robin over question types): 55 tuning, 10 held-out. Real LLM calls: 80, cache hits: 37.

**Read with care.** Every table below except the held-out section uses only the tuning set. Settings are chosen from tuning-set results, so those numbers are optimistic; the held-out questions (written by the project owner) are never used to choose settings and give the unbiased check. Every percentage shows its counts.

## Status (all items)

Items with an error (the LLM kept failing, e.g. 503) or skipped (budget or quota used up) are left out of every metric; they are not counted as wrong.

| Status | items |
|---|---|
| ok | 65 |

## Refusals (tuning set)

Which layer refused: retrieval (nothing similar enough, `no_relevant_chunks`) or the model (it said the answer isn't in the documents, `model_declined`). For answerable questions and follow-ups, every refusal is a false refusal.

| Type | n | refused | by retrieval | by the model | answered |
|---|---|---|---|---|---|
| answerable | 31 | 6% (2/31) | 0% (0/31) | 6% (2/31) | 94% (29/31) |
| follow_up | 8 | 25% (2/8) | 0% (0/8) | 25% (2/8) | 75% (6/8) |
| unanswerable_off_topic | 8 | 100% (8/8) | 38% (3/8) | 62% (5/8) | 0% (0/8) |
| unanswerable_on_topic | 8 | 100% (8/8) | 0% (0/8) | 100% (8/8) | 0% (0/8) |

## Citations (tuning set)

Answered questions that have expected pages.

| answers | cited sources on an expected page | ≥1 correct citation | no citation |
|---|---|---|---|
| 35 | 86% (36/42) | 97% (34/35) | 0% (0/35) |

## Faithfulness (LLM judge, tuning set)

The judge is the same Gemini model that wrote the answers: the same model family as the answerer, which tends to agree with its own kind, so these scores are **biased upwards**. Each answer is split into claims and checked against the full text of the passages it cites; uncited answers aren't judged. Judge failures: 0.

| judged answers | supported claims | fully supported answers |
|---|---|---|
| 35 | 100% (46/46) | 100% (35/35) |

## Follow-up rewrites (tuning set)

| follow-ups | fell back to the original | same meaning as expected (judge) | hit@5 with the actual rewrite |
|---|---|---|---|
| 8 | 0% (0/8) | 62% (5/8) | 88% (7/8) |

## Held-out set (owner-written, never used to choose settings)

| Type | n | refused | by retrieval | by the model | answered |
|---|---|---|---|---|---|
| answerable | 6 | 17% (1/6) | 0% (0/6) | 17% (1/6) | 83% (5/6) |
| unanswerable_off_topic | 2 | 100% (2/2) | 100% (2/2) | 0% (0/2) | 0% (0/2) |
| unanswerable_on_topic | 2 | 100% (2/2) | 0% (0/2) | 100% (2/2) | 0% (0/2) |

| Questions | n | off-topic refused | on-topic unanswerable refused | false refusals | ≥1 correct citation | supported claims |
|---|---|---|---|---|---|---|
| tuning set | 55 | 100% (8/8) | 100% (8/8) | 10% (4/39) | 97% (34/35) | 100% (46/46) |
| held-out (owner-written) | 10 | 100% (2/2) | 100% (2/2) | 17% (1/6) | 100% (5/5) | 100% (5/5) |
