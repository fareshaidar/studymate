# Retrieval evaluation

Run 2026-10-08 23:37, commit `6675e5b`.

| Setting | Value |
|---|---|
| embedding_model | BAAI/bge-small-en-v1.5 |
| min_similarity | 0.55 |
| retrieval_top_k | 8 |
| min_alnum_ratio | 0.5 |
| history_window | 6 |

Dataset: 65 questions. Tuning set: 55 (answerable: 31, follow_up: 8, unanswerable_off_topic: 8, unanswerable_on_topic: 8). Held-out set, written by the project owner: 10 (answerable: 6, unanswerable_off_topic: 2, unanswerable_on_topic: 2).

**Read with care.** Every sweep, score distribution and "tuning set" row uses only the tuning set, and settings are chosen from those, so the numbers at a chosen setting are optimistic. The held-out questions are never used to choose settings; they appear only in the held-out rows and give the unbiased check. Every percentage shows its counts: with this few questions, one question moves a rate by several points.

Relevance is per page: a chunk counts if its page is one of the item's expected pages. Follow-ups are searched as their expected standalone question (a perfect rewrite) unless stated otherwise.

## Ranking quality (no threshold)

Answerable questions and follow-ups only; unusable (diagram) chunks are skipped, as in the chat.

| Questions | n | hit@1 | hit@3 | hit@5 | hit@8 | hit@10 | recall@1 | recall@3 | recall@5 | recall@8 | recall@10 | MRR |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| all (tuning set) | 39 | 0.62 | 0.79 | 0.87 | 0.95 | 0.95 | 0.59 | 0.77 | 0.86 | 0.94 | 0.94 | 0.71 |
| reworded tuning questions | 31 | 0.35 | 0.55 | 0.68 | 0.71 | 0.74 | 0.34 | 0.53 | 0.66 | 0.69 | 0.73 | 0.48 |
| held-out (owner-written) | 6 | 0.50 | 0.67 | 0.83 | 0.83 | 0.83 | 0.50 | 0.67 | 0.83 | 0.83 | 0.83 | 0.59 |
| follow-ups as typed | 8 | 0.25 | 0.25 | 0.38 | 0.50 | 0.62 | 0.25 | 0.25 | 0.38 | 0.50 | 0.62 | 0.30 |
| follow-ups, expected standalone | 8 | 0.62 | 0.75 | 0.75 | 0.88 | 0.88 | 0.56 | 0.69 | 0.69 | 0.81 | 0.81 | 0.69 |

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

## min_similarity sweep (tuning set, top_k = 8)

What the retrieval layer alone does. A question that reaches the LLM can still be declined by the model, so 'reach LLM' is an upper bound on false answers.

| min_similarity | false refusals (answerable) | expected page kept (answerable) | reach LLM: off-topic | reach LLM: on-topic unanswerable | mean passages |
|---|---|---|---|---|---|
| 0.45 | 0% (0/39) | 95% (37/39) | 100% (8/8) | 100% (8/8) | 7.8 |
| 0.475 | 0% (0/39) | 95% (37/39) | 88% (7/8) | 100% (8/8) | 7.9 |
| 0.5 | 0% (0/39) | 95% (37/39) | 62% (5/8) | 100% (8/8) | 8.0 |
| 0.525 | 0% (0/39) | 95% (37/39) | 62% (5/8) | 100% (8/8) | 8.0 |
| 0.55 | 0% (0/39) | 95% (37/39) | 62% (5/8) | 100% (8/8) | 7.8 |
| 0.575 | 0% (0/39) | 95% (37/39) | 38% (3/8) | 100% (8/8) | 7.8 |
| 0.6 | 0% (0/39) | 92% (36/39) | 12% (1/8) | 100% (8/8) | 7.4 |
| 0.625 | 3% (1/39) | 92% (36/39) | 0% (0/8) | 88% (7/8) | 6.8 |
| 0.65 | 5% (2/39) | 87% (34/39) | 0% (0/8) | 88% (7/8) | 5.5 |
| 0.675 | 13% (5/39) | 77% (30/39) | 0% (0/8) | 50% (4/8) | 4.4 |
| 0.7 | 18% (7/39) | 64% (25/39) | 0% (0/8) | 25% (2/8) | 2.9 |

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
| 0.55 | 0% (0/6) | 83% (5/6) | 0% (0/2) | 100% (2/2) | 8.0 |

## min_alnum_ratio

Chunks the diagram filter would drop at each ratio.

| min_alnum_ratio | chunks dropped | of which on a page a tuning question expects |
|---|---|---|
| 0.3 | 0% (2/849) | 0 |
| 0.4 | 0% (3/849) | 0 |
| 0.5 | 1% (5/849) | 0 |
| 0.6 | 1% (11/849) | 0 |
| 0.7 | 4% (35/849) | 0 |

## Front-matter filter (Phase 9)

At min_similarity 0.55 and top_k 8, computed from the same searches with the filter off and on. Tuning: the original tuning questions (follow-ups as their expected standalone question). Reworded: the same answerable tuning questions in other words. Held-out: reported only, never used to choose. App setting during this run: exclude_front_matter = False.

| Metric | Tuning off | Tuning on | Reworded off | Reworded on | Held-out off | Held-out on |
|---|---|---|---|---|---|---|
| hit@8 (usable ranking) | 95% (37/39) | 95% (37/39) | 71% (22/31) | 71% (22/31) | 83% (5/6) | 83% (5/6) |
| hit@5 (usable ranking) | 87% (34/39) | 87% (34/39) | 68% (21/31) | 71% (22/31) | 83% (5/6) | 83% (5/6) |
| expected page kept | 95% (37/39) | 95% (37/39) | 71% (22/31) | 71% (22/31) | 83% (5/6) | 83% (5/6) |
| false refusals (retrieval) | 0% (0/39) | 0% (0/39) | 0% (0/31) | 0% (0/31) | 0% (0/6) | 0% (0/6) |
| front-matter slots / kept slots | 4% (11/312) | 0% (0/312) | 3% (7/248) | 0% (0/248) | 0% (0/48) | 0% (0/48) |
| questions with ≥1 front-matter slot | 23% (9/39) | 0% (0/39) | 16% (5/31) | 0% (0/31) | 0% (0/6) | 0% (0/6) |
| mean passages | 7.81 | 7.81 | 8.00 | 8.00 | 8.00 | 8.00 |
| reach LLM: off-topic | 62% (5/8) | 62% (5/8) | – (0/0) | – (0/0) | 0% (0/2) | 0% (0/2) |
| reach LLM: on-topic unanswerable | 100% (8/8) | 100% (8/8) | – (0/0) | – (0/0) | 100% (2/2) | 100% (2/2) |

### Chunks the rule flags (whole evaluation index)

20 chunks flagged; on a page a tuning question expects: 0; on a held-out expected page: 0.

| Document | flagged | pages |
|---|---|---|
| skylab | 20 | 13, 14, 14, 15, 15, 16, 16, 17, 17, 18, 18, 19, 19, 20, 20, 21, 21, 22, 22, 23 |

### Front-matter passages the filter removes

Passages the model is given with the filter off (at the settings above).

| Set | Question | rank | page | chunk | score |
|---|---|---|---|---|---|
| Tuning | sky-02 | 3 | skylab p13 | 11 | 0.640 |
| Tuning | sky-03 | 7 | skylab p19 | 23 | 0.669 |
| Tuning | sky-04 | 2 | skylab p18 | 20 | 0.684 |
| Tuning | sky-04 | 3 | skylab p13 | 11 | 0.678 |
| Tuning | sky-11 | 6 | skylab p22 | 29 | 0.662 |
| Tuning | sky-12 | 8 | skylab p22 | 29 | 0.620 |
| Tuning | sky-13 | 6 | skylab p22 | 29 | 0.635 |
| Tuning | fu-01 | 2 | skylab p13 | 11 | 0.676 |
| Tuning | fu-01 | 4 | skylab p18 | 20 | 0.662 |
| Tuning | fu-02 | 8 | skylab p18 | 20 | 0.668 |
| Tuning | fu-03 | 4 | skylab p17 | 18 | 0.669 |
| Tuning | on-04 | 8 | skylab p21 | 26 | 0.575 |
| Reworded | rw-sky-04 | 1 | skylab p13 | 11 | 0.741 |
| Reworded | rw-sky-04 | 3 | skylab p18 | 20 | 0.713 |
| Reworded | rw-sky-06 | 1 | skylab p13 | 11 | 0.717 |
| Reworded | rw-sky-06 | 2 | skylab p18 | 20 | 0.699 |
| Reworded | rw-sky-07 | 2 | skylab p13 | 11 | 0.675 |
| Reworded | rw-sky-13 | 7 | skylab p22 | 29 | 0.657 |
| Reworded | rw-cam-01 | 6 | skylab p21 | 26 | 0.669 |
| Held-out | user-08 | 5 | skylab p21 | 26 | 0.667 |
