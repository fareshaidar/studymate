# Retrieval evaluation

Run 2026-10-08 19:03, commit `2aafa58`.

| Setting | Value |
|---|---|
| embedding_model | BAAI/bge-small-en-v1.5 |
| min_similarity | 0.55 |
| retrieval_top_k | 5 |
| min_alnum_ratio | 0.5 |
| history_window | 6 |

Dataset: 65 questions. Tuning set: 55 (answerable: 31, follow_up: 8, unanswerable_off_topic: 8, unanswerable_on_topic: 8). Held-out set, written by the project owner: 10 (answerable: 6, unanswerable_off_topic: 2, unanswerable_on_topic: 2).

**Read with care.** Every sweep, score distribution and "tuning set" row uses only the tuning set, and settings are chosen from those, so the numbers at a chosen setting are optimistic. The held-out questions are never used to choose settings; they appear only in the held-out rows and give the unbiased check. Every percentage shows its counts: with this few questions, one question moves a rate by several points.

Relevance is per page: a chunk counts if its page is one of the item's expected pages. Follow-ups are searched as their expected standalone question (a perfect rewrite) unless stated otherwise.

## Ranking quality (no threshold)

Answerable questions and follow-ups only; unusable (diagram) chunks are skipped, as in the chat.

| Questions | n | hit@1 | hit@3 | hit@5 | hit@10 | recall@1 | recall@3 | recall@5 | recall@10 | MRR |
|---|---|---|---|---|---|---|---|---|---|---|
| all (tuning set) | 39 | 0.62 | 0.79 | 0.87 | 0.95 | 0.59 | 0.77 | 0.86 | 0.94 | 0.71 |
| held-out (owner-written) | 6 | 0.50 | 0.67 | 0.83 | 0.83 | 0.50 | 0.67 | 0.83 | 0.83 | 0.59 |
| follow-ups as typed | 8 | 0.25 | 0.25 | 0.38 | 0.62 | 0.25 | 0.25 | 0.38 | 0.62 | 0.30 |
| follow-ups, expected standalone | 8 | 0.62 | 0.75 | 0.75 | 0.88 | 0.56 | 0.69 | 0.69 | 0.81 | 0.69 |

## Best score per question (tuning set)

| Type | n | min | p25 | median | p75 | max |
|---|---|---|---|---|---|---|
| answerable | 31 | 0.620 | 0.703 | 0.731 | 0.765 | 0.807 |
| follow_up | 8 | 0.715 | 0.733 | 0.748 | 0.755 | 0.758 |
| unanswerable_off_topic | 8 | 0.471 | 0.492 | 0.567 | 0.593 | 0.607 |
| unanswerable_on_topic | 8 | 0.611 | 0.652 | 0.685 | 0.700 | 0.709 |

| best score | answerable | off-topic | on-topic unanswerable |
|---|---|---|---|
| 0.30–0.35 |  |  |  |
| 0.35–0.40 |  |  |  |
| 0.40–0.45 |  |  |  |
| 0.45–0.50 |  | ███ 3 |  |
| 0.50–0.55 |  |  |  |
| 0.55–0.60 |  | ████ 4 |  |
| 0.60–0.65 | ██ 2 | █ 1 | █ 1 |
| 0.65–0.70 | █████ 5 |  | █████ 5 |
| 0.70–0.75 | ██████████████████ 18 |  | ██ 2 |
| 0.75–0.80 | █████████████ 13 |  |  |
| 0.80–0.85 | █ 1 |  |  |
| 0.85–0.90 |  |  |  |

Held-out set:

| Type | n | min | p25 | median | p75 | max |
|---|---|---|---|---|---|---|
| answerable | 6 | 0.722 | 0.747 | 0.764 | 0.779 | 0.790 |
| unanswerable_off_topic | 2 | 0.501 | 0.502 | 0.503 | 0.503 | 0.504 |
| unanswerable_on_topic | 2 | 0.568 | 0.597 | 0.626 | 0.656 | 0.685 |

## min_similarity sweep (tuning set, top_k = 5)

What the retrieval layer alone does. A question that reaches the LLM can still be declined by the model, so 'reach LLM' is an upper bound on false answers.

| min_similarity | false refusals (answerable) | expected page kept (answerable) | reach LLM: off-topic | reach LLM: on-topic unanswerable | mean passages |
|---|---|---|---|---|---|
| 0.45 | 0% (0/39) | 87% (34/39) | 100% (8/8) | 100% (8/8) | 4.9 |
| 0.475 | 0% (0/39) | 87% (34/39) | 88% (7/8) | 100% (8/8) | 4.9 |
| 0.5 | 0% (0/39) | 87% (34/39) | 62% (5/8) | 100% (8/8) | 5.0 |
| 0.525 | 0% (0/39) | 87% (34/39) | 62% (5/8) | 100% (8/8) | 5.0 |
| 0.55 | 0% (0/39) | 87% (34/39) | 62% (5/8) | 100% (8/8) | 4.9 |
| 0.575 | 0% (0/39) | 87% (34/39) | 38% (3/8) | 100% (8/8) | 5.0 |
| 0.6 | 0% (0/39) | 85% (33/39) | 12% (1/8) | 100% (8/8) | 4.8 |
| 0.625 | 3% (1/39) | 85% (33/39) | 0% (0/8) | 88% (7/8) | 4.6 |
| 0.65 | 5% (2/39) | 82% (32/39) | 0% (0/8) | 88% (7/8) | 4.1 |
| 0.675 | 13% (5/39) | 74% (29/39) | 0% (0/8) | 50% (4/8) | 3.4 |
| 0.7 | 18% (7/39) | 64% (25/39) | 0% (0/8) | 25% (2/8) | 2.5 |

## retrieval_top_k sweep (tuning set, min_similarity = 0.55)

| top_k | false refusals (answerable) | expected page kept (answerable) | reach LLM: off-topic | reach LLM: on-topic unanswerable | mean passages |
|---|---|---|---|---|---|
| 1 | 0% (0/39) | 62% (24/39) | 62% (5/8) | 100% (8/8) | 1.0 |
| 3 | 0% (0/39) | 79% (31/39) | 62% (5/8) | 100% (8/8) | 3.0 |
| 5 | 0% (0/39) | 87% (34/39) | 62% (5/8) | 100% (8/8) | 4.9 |
| 8 | 0% (0/39) | 95% (37/39) | 62% (5/8) | 100% (8/8) | 7.8 |
| 10 | 0% (0/39) | 95% (37/39) | 62% (5/8) | 100% (8/8) | 9.7 |

Held-out set at the current settings (not used to choose them):

| min_similarity | false refusals (answerable) | expected page kept (answerable) | reach LLM: off-topic | reach LLM: on-topic unanswerable | mean passages |
|---|---|---|---|---|---|
| 0.55 | 0% (0/6) | 83% (5/6) | 0% (0/2) | 100% (2/2) | 5.0 |

## min_alnum_ratio

Chunks the diagram filter would drop at each ratio.

| min_alnum_ratio | chunks dropped | of which on a page a tuning question expects |
|---|---|---|
| 0.3 | 0% (2/849) | 0 |
| 0.4 | 0% (3/849) | 0 |
| 0.5 | 1% (5/849) | 0 |
| 0.6 | 1% (11/849) | 0 |
| 0.7 | 4% (35/849) | 0 |

## Chunk size (tuning set)

Each size re-indexed into its own temporary store.

| max_chars | overlap | chunks | hit@1 | hit@5 | MRR | false refusals | reach LLM: on-topic |
|---|---|---|---|---|---|---|---|
| 1000 | 150 | 1339 | 67% (26/39) | 90% (35/39) | 0.77 | 0% (0/39) | 100% (8/8) |
| 1800 | 250 | 849 | 62% (24/39) | 87% (34/39) | 0.71 | 0% (0/39) | 100% (8/8) |
| 2500 | 350 | 735 | 56% (22/39) | 85% (33/39) | 0.67 | 0% (0/39) | 100% (8/8) |
