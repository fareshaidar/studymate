# Phase 7: Evaluation

## What was built

- **Dataset** (`backend/evaluation/datasets/studymate_eval.json`): 65 questions over three PDFs,
  each typed `answerable`, `follow_up`, `unanswerable_off_topic` or `unanswerable_on_topic`.
  - **Tuning set:** 55 items written by Claude (31 answerable, 8 follow-ups, 8 off-topic,
    8 on-topic unanswerable).
  - **Held-out set:** 10 items by the owner (`"author": "user"`): 6 answerable, 2 off-topic,
    2 on-topic unanswerable. They were drafted with AI help and reviewed by the owner.
  - **Answerable items** list the expected document, the expected pages (any of them counts) and
    a short evidence quote copied from the PDF. Follow-ups also carry the earlier turns and the
    expected standalone question.
- **Documents:**
  - Skylab Crew Systems Mission Evaluation, NASA, 1974, 398 pages.
  - Space Telescope Focal Plane Camera report, Itek for NASA, 1976, 114 pages.
  - IPCC AR6 Synthesis Report, Summary for Policymakers, 42 pages.

  The two NASA reports are OCR scans. The PDFs are **not in git**; each runner reads them from
  `--documents` (default: the git-ignored `backend/evaluation/datasets/documents/`) and checks
  each file's SHA-256, so the ground truth can't silently point at a different version.
- **`check_dataset.py`** checks the ground truth against the PDFs:
  - every expected page contains one of the item's evidence quotes;
  - it lists other pages that also contain a quote (they may belong in `pages`);
  - it writes a git-ignored review sheet for checking by hand.
- **Small app changes so evaluation reuses the real code:**
  - `retrieve()` was split out of `answer_question`;
  - `ingest_pdf` accepts chunk sizes;
  - `ChatResult.passages` holds the full text the model saw. It is never stored or returned by
    the API.
- **`metrics.py`:** pure functions, unit-tested with tiny hand-made examples.
  - hit@k, recall@k, MRR;
  - score distributions;
  - threshold, top-k, `min_alnum_ratio` and chunk-size sweeps;
  - refusal, citation, faithfulness and rewrite metrics.

  Every rate keeps its counts, so reports show the n.
- **`harness.py`:**
  - builds a temporary SQLite + Chroma index with the app's own `ingest_pdf`;
  - refuses any path inside `backend/data` or `settings.data_dir`;
  - wraps the LLM in `CachedLLM`: reply cache, `--max-calls` cap, about 1 s between real calls,
    with one shared `RunState` for the answerer and the judge;
  - `run_case` retries an item after 429/503 errors and records a persistent failure as an
    error, never as a wrong answer.
- **`run_retrieval_eval.py`** (no LLM, free): ranks every question once with `retrieve()` and
  computes all metrics and sweeps from that one ranking. `--chunk-sweep` re-indexes per chunk
  size.
- **`run_answer_eval.py`** (uses the LLM):
  - runs `answer_question` on every item, follow-up history included;
  - an LLM judge checks faithfulness against the full cited passages and whether each rewrite
    means the same as the expected standalone question;
  - modes: real Gemini, `--fake-llm`, `--no-llm`; `--limit N` picks items round-robin over
    question types.
- **Held-out separation:** every sweep, score distribution and "tuning set" row uses only the
  tuning items. The held-out items appear only in their own rows. Tests check that removing
  them leaves every tuning result identical, so they can never influence a setting choice.

## How the pieces connect

```
studymate_eval.json ─► dataset.py (schema, SHA-256 check) ─► harness.temporary_index (ingest_pdf → temp SQLite + Chroma)
   retrieval: retrieve(query, top_k=10, min_similarity=-1) ─► RankedChunk list per question
              ─► metrics: ranking, kept_chunks (mirrors retrieve's cutoff; a drift test keeps them equal), sweeps
   answers:   answer_question (CachedLLM) ─► ChatResult (reason, cited sources, full passages)
              ─► judge via generate_json (faithfulness, rewrite meaning) ─► AnswerCase ─► metrics
   both:      tuning items → all tables and sweeps; owner-written items → held-out rows only
              ─► results/*.json (git-ignored) + markdown report
```

## How to run (from `backend/`)

```powershell
.\.venv\Scripts\python -m evaluation.check_dataset                     # ground truth vs PDFs
.\.venv\Scripts\python -m evaluation.run_retrieval_eval --chunk-sweep  # ~10 min, no LLM
.\.venv\Scripts\python -m evaluation.run_answer_eval --limit 20        # real Gemini, ~35 calls
.\.venv\Scripts\python -m evaluation.run_answer_eval                   # the rest; cached replies are free
.\.venv\Scripts\python -m evaluation.run_answer_eval --fake-llm        # plumbing check, no key
.\.venv\Scripts\python -m evaluation.run_answer_eval --no-llm          # retrieval-layer refusals only
.\.venv\Scripts\python -m evaluation.run_answer_eval --top-k 8         # override top_k for this run only; files tagged -topk8
```

Use `--documents DIR` if the PDFs live elsewhere. The baseline reports are copied unchanged in
`docs/evaluation/`: `retrieval-baseline.md` and `answer-baseline.md`, both from commit
`2aafa58`. Neither contains any PDF text: they share no 6-word run with the extracted PDFs.

## Baseline results (settings at the time: min_similarity 0.55, top_k 5, 1800/250 chunks)

### Retrieval
Answerable questions plus follow-ups; follow-ups are searched as their expected standalone question.

| | n | hit@1 | hit@5 | hit@10 | MRR |
|---|---|---|---|---|---|
| tuning set | 39 | 24/39 | 34/39 | 37/39 | 0.71 |
| held-out | 6 | 3/6 | 5/6 | 5/6 | 0.59 |

- **Follow-ups (tuning set, n = 8):** searched as typed, hit@5 is 3/8. Searched as the expected
  standalone question, it's 6/8. With the model's actual rewrites it's 7/8 (answer run), but one
  of those 7 (fu-06) reached only an unhelpful passage of the right page.
- **Best score per question (tuning set):**
  - answerable: 0.62–0.81;
  - off-topic: 0.47–0.61;
  - on-topic unanswerable: 0.61–0.71, inside the answerable range.
- **min_similarity (tuning set):**
  - at 0.55, 5/8 off-topic and 8/8 on-topic unanswerable questions reach the LLM, with 0/39
    false refusals;
  - at 0.60, off-topic drops to 1/8, still with 0/39 false refusals;
  - from 0.625, answerable questions start being refused.
- **top_k 5 → 8 (tuning set):** an expected page is kept for 37/39 instead of 34/39, for 7.8
  instead of 4.9 passages per prompt.
- **Chunk size (tuning set):** 1000/150 gives hit@1 26/39 against 24/39 for 1800/250 and 22/39
  for 2500/350. That's within noise at n = 39.
- **min_alnum_ratio:** 0.5 drops 5 of 849 chunks, none on an expected page.

### Answers (real Gemini, all 65 items, 80 real calls, 0 errors)

| | n | false refusals | off-topic refused | on-topic unanswerable refused | ≥1 correct citation | supported claims (judge) |
|---|---|---|---|---|---|---|
| tuning set | 55 | 4/39 | 8/8 | 8/8 | 34/35 | 46/46 |
| held-out | 10 | 1/6 | 2/2 | 2/2 | 5/5 | 5/5 |

- **Which layer refused (tuning set):**
  - off-topic: retrieval 3, model 5;
  - on-topic unanswerable: model 8;
  - every false refusal: the model.
- **Citations (tuning set):** 36/42 cited sources are on an expected page, and no answer is
  uncited.
- **Rewrites (tuning set):** 0/8 fell back to the original question, and the judge rated 5/8 as
  meaning the same as the expected question.

## Main findings

1. **The two refusal layers split the work.** Retrieval stops clearly off-topic questions (all
   held-out ones score about 0.50). On-topic questions the documents don't answer score like
   answerable ones (0.61–0.71), so no threshold can separate them, and the model's "not found"
   rule caught all 10.
2. **False refusals come from retrieval, not the prompt.** All 5 were traced (4 tuning,
   1 held-out). For the 4 tuning items, the exact prompts were rebuilt and the raw replies found
   in the reply cache, with no new LLM calls. In every case the passage containing the answer was
   **not among the 5 shown to the model**, so its "not found" was correct for what it saw.

   | Item | Answer passage rank | Why it lost |
   |---|---|---|
   | sky-04 | 8th | The table of contents and the list of figures (OCR front matter) took 2 of the 5 slots. |
   | sky-13 | 8th | Five other passages from the same twin-pole-sail section scored 0.639–0.659 against 0.628. |
   | fu-06 | 7th | Page 10 *was* in the top 5, but only as its footnotes passage; the A.1.1 passage with the land/ocean figures ranked 7th. |
   | fu-01 | not in top 60 | The answer is one sentence at the top of a page whose chunk is mostly about wipes. |
   | user-06 (held-out) | not in top 10 | Neighbouring filter-wheel pages (77, 80) outrank page 85. |

   In 3 of 5 the answer passage ranked 7th or 8th; `top_k` 8 would have shown it for sky-04,
   sky-13 and fu-06 (ranks 1–8 are all usable and above 0.55). In 2 of 5 it was out of reach
   of any top_k considered.
3. **Rewriting follow-ups is worth its LLM call:** hit@5 goes from 3/8 as typed to 7/8 with the
   model's rewrites. One of those 7 (fu-06) reached only the right page's footnotes, not the
   answer.

## Settings worth considering (not applied; the owner decides)

- **`min_similarity` 0.60:** off-topic questions reaching the LLM drop from 5/8 to 1/8, with no
  false refusals on the tuning set. The 2 held-out off-topic questions score about 0.50, so they
  are refused at both 0.55 and 0.60 and can't confirm the change.
- **`retrieval_top_k` 8:** an expected page is kept for 3 more tuning questions (37/39), for
  about 60% more prompt text. A full answer run with this value is described in
  "top_k 8 experiment" below; the default stays at 5.

  **Update (Phase 9):** `retrieval_top_k` 8 is now the default. `min_similarity` 0.60 is still
  not applied, and the front-matter filter was measured and kept off (below).
- **Front-matter filtering:** a check for tables of contents and lists of figures. Raising
  `min_alnum_ratio` to 0.6 would drop the table of contents (0.57) but not the list of figures
  (0.77).

  **Update (Phase 9):** built as a dot-leader rule behind `exclude_front_matter` and measured at
  top_k 8. It flags only the 20 Skylab contents/list chunks and frees 11 of 312 kept passages on
  the tuning set, but "expected page kept" and hit@8 don't change (37/39 tuning, 22/31 reworded,
  5/6 held-out), so it stays **off** by the rule set before measuring. See the README and
  [front-matter-filter.md](../evaluation/front-matter-filter.md).
- After any change, rerun both evaluations and check the held-out rows, which weren't used to
  choose it.

## top_k 8 experiment

Run with `run_answer_eval --top-k 8 --max-calls 150`. The option overrides `retrieval_top_k`
for that evaluation process only. **The app default stays at 5.**

**Update (Phase 9):** the app default is now 8, based on this experiment.

- **Calls:** 89 real calls and 30 cache hits, with no errors and nothing skipped.
- **Baseline:** the 19:11 run, re-run from the reply cache with `--top-k 5 --max-calls 0` to get
  passage counts and prompt sizes. That made 0 real calls and reproduced all 65 records.

| | Tuning (n=55) top_k 5 | Tuning top_k 8 | Held-out (n=10) top_k 5 | Held-out top_k 8 |
|---|---|---|---|---|
| Answerable false refusals | 2/31 | 0/31 | 1/6 | 1/6 |
| Follow-up false refusals | 2/8 | 1/8 | – | – |
| Off-topic refused | 8/8 | 8/8 | 2/2 | 2/2 |
| On-topic unanswerable refused | 8/8 | 8/8 | 2/2 | 2/2 |
| Answers with ≥1 correct citation | 34/35 | 36/38 | 5/5 | 5/5 |
| Cited sources on expected pages | 36/42 | 39/47 | 6/6 | 6/6 |
| Supported claims (judge) | 46/46 | 53/53 | 5/5 | 5/5 |
| Mean passages per answer call | 4.92 | 7.81 | 5.00 | 8.00 |
| Mean prompt characters per answer call | 6,775 | 10,247 | 7,012 | 10,913 |

- **The traced false refusals:**
  - **Now answered:** sky-04, sky-13 and fu-06, whose answer passages had ranked 7th–8th. All 3
    answers match the reference answer and cite the expected page.
  - **Still declined:** fu-01 (answer passage not in the top 60) and user-06 (not in the
    top 10). The trace predicted all 5 outcomes.
- **No unanswerable question was answered.** All 20 are still refused, each by the same layer
  as before: off-topic 5 by retrieval and 5 by the model; on-topic 10 by the model.
- **Side effects on the tuning set:**
  - **sky-01** is now answered correctly but with no citation, while at top_k 5 it was cited.
  - **Off-page citations** go from 6 to 8: ipcc-06 adds page 37 next to the correct page 11,
    and cam-02 adds page 7 but still has no correct citation. Some may be valid pages missing
    from the ground truth.
- **Cost:** about 59% more passages per answer call, and 51% (tuning) to 56% (held-out) more
  prompt characters.
- **Caveats:**
  - **Proposed after tracing the misses:** top_k 8 was proposed after tracing these same misses,
    so their recovery was predicted rather than independent evidence.
  - **Not confirmed by the held-out set:** its only false refusal (user-06) is beyond the top 10,
    and every held-out number is unchanged.
  - **Small sample:** the gain rests on 3 questions, each from one run of a non-deterministic
    model.
  - **Faithfulness:** the judge, the same model family as the answerer, rates both settings
    100%, so it can't tell them apart.

## Limitations

- **Small n.** One question moves a tuning rate by 2.6 points (1/39) and a held-out rate by
  17 points (1/6). The held-out set has 6 answerable questions, no follow-ups, and only 2
  off-topic questions, which can't confirm a threshold.
- **Ground truth.**
  - **Who wrote it:** Claude wrote the 55 tuning questions while reading the pages, which tends
    to reuse the documents' wording and flatter retrieval. The held-out questions were drafted
    with AI help and reviewed by the owner.
  - **Page relevance:** it is judged against the listed pages only. A valid page missing from
    the list counts as wrong; for example cam-04 cites page 89, the camera's power-profile page.
    So citation precision (36/42) is a lower bound.
  - **Figure pages:** questions avoid the OCR'd figure pages, so the `min_alnum_ratio` sweep
    can't show harm from the filter.
  - **Pages, not passages:** hit@k and "expected page kept" count a hit when *any* passage of
    the right page is retrieved, even one without the answer. fu-06 is such a case: page 10's
    footnotes were shown, its answer passage wasn't. So these rates can overstate what the model
    actually receives; evidence-quote matching per passage would be stricter.
- **The judge is the same model family as the answerer**, which tends to agree with it. The
  46/46 supported claims are biased upwards and weren't spot-checked by a person. The rewrite
  judge (5/8 same meaning) is stricter than page-level retrieval success (7/8 hit@5). In fu-06
  it was right: the rewrite dropped the 2011–2020 period, and retrieval only reached the page's
  footnotes.
- **Settings are chosen on the tuning set,** so tuning-set numbers at a chosen setting are
  optimistic.
- **Reruns aren't new samples.** The reply cache makes a rerun reproduce the same answers; to
  measure run-to-run variation, use a fresh cache.

## Interview questions

1. **Q: Why evaluate retrieval separately from the answers?**
   A: It isolates the layers, and it's free. Retrieval needs no LLM, so I can rank every question
   once with the same `retrieve()` the app uses. Every threshold and top-k setting is then
   computed offline from that one ranking: 11 thresholds and 5 top-k values cost no extra
   searches and zero API calls. The sweep re-implements the cutoff, so a drift test runs both on the same
   index and checks they keep exactly the same chunks. When an answer goes wrong, the retrieval
   numbers tell me whether the model ever saw the right page.

2. **Q: How did you avoid tuning your settings to your test set?**
   A: The dataset has a tuning set (55 questions) and a held-out set (10 questions written by the
   owner). Every sweep and every "tuning set" row uses only the tuning items; the held-out ones
   only appear in their own rows. A test runs the evaluation with and without the held-out items
   and checks that every tuning result is identical, so they provably can't influence a choice.
   I also print the counts next to every percentage, because at n = 6, one question is
   17 points.

3. **Q: How do you measure faithfulness, and what's the weakness?**
   A: An LLM judge gets the answer and the full text of only the passages it cites. It splits the
   answer into claims and marks each supported or not; outside knowledge doesn't count. The reply
   is validated with Pydantic, with one retry. The weakness is that the judge is the same model
   family as the answerer and tends to agree with it, so the 46/46 is biased upwards. The report
   says so. Better checks would be a different model family as judge, or spot-checking a sample
   by hand.

4. **Q: How did you keep the evaluation within a free-tier API budget and robust to outages?**
   A: Every LLM call goes through a wrapper that does four things:
   - caches replies by model, system prompt and prompt, so a rerun or a resumed run only pays
     for new prompts;
   - stops at `--max-calls`;
   - waits about a second between real calls;
   - shares one budget, pause and cache between the answerer and the judge.

   Transient 429/503 errors are retried after 30 s and then 60 s. If they persist, the item is
   recorded as an error and left out of every metric, so an outage never counts as a wrong
   answer. The daily quota stops the run cleanly with partial results.

5. **Q: Walk me through a failure you diagnosed.**
   A: Five answerable questions were refused; I traced all of them. For the tuning ones I rebuilt
   the exact prompts and found the raw model replies in the cache, so no new API calls were
   needed. Two examples: In one, the right page ranked 8th, just
   outside top_k 5, and the table of contents and the list of figures from the OCR scan took 2 of
   the 5 slots. In the other, the answer was one sentence at the top of a page whose chunk was
   mostly about something else, so it never ranked. In both cases the model was right to decline
   what it was shown. So the fix belongs in retrieval (top_k, a front-matter filter, chunking),
   not in a looser prompt, which would trade correct refusals for invented answers.
