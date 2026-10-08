import pytest

from evaluation.metrics import (
    AnswerCase,
    RankedChunk,
    Rate,
    RetrievalCase,
    alnum_sweep,
    citation_metrics,
    distribution,
    evaluate_cutoff,
    faithfulness_metrics,
    hit_at_k,
    kept_chunks,
    mean,
    ranking_metrics,
    recall_at_k,
    reciprocal_rank,
    refusal_metrics,
    rewrite_metrics,
    status_counts,
    threshold_sweep,
    top_k_sweep,
    top_scores_by_type,
)

A1, A2, A3 = ("a", 1), ("a", 2), ("a", 3)
B1 = ("b", 1)


def chunk(page, score, usable=True):
    return RankedChunk(page=page, score=score, usable=usable)


# --- basics ---


def test_rate_and_mean():
    assert Rate(1, 4).value == 0.25
    assert Rate(0, 0).value is None
    assert mean([]) is None
    assert mean([1, 2]) == 1.5


# --- ranking ---


def test_hit_at_k():
    pages = [B1, A2, A1]
    assert hit_at_k(pages, {A2}, 1) is False
    assert hit_at_k(pages, {A2}, 2) is True
    assert hit_at_k([], {A2}, 5) is False


def test_recall_at_k_counts_distinct_expected_pages():
    pages = [A1, A1, B1, A2]
    assert recall_at_k(pages, {A1, A2}, 3) == 0.5  # A1 twice still counts once
    assert recall_at_k(pages, {A1, A2}, 4) == 1.0
    with pytest.raises(ValueError):
        recall_at_k(pages, set(), 3)


def test_reciprocal_rank():
    assert reciprocal_rank([B1, A3, A1], {A1, A3}) == 0.5  # first relevant at rank 2
    assert reciprocal_rank([A1], {A1}) == 1.0
    assert reciprocal_rank([B1], {A1}) == 0.0


def test_ranking_metrics_skip_unusable_chunks_and_unanswerable_questions():
    cases = [
        # The diagram chunk on A1 ranks first but is never shown, so A2 is rank 1.
        RetrievalCase("q1", "answerable", [chunk(A1, 0.9, usable=False), chunk(A2, 0.8)], {A2}),
        RetrievalCase("q2", "follow_up", [chunk(B1, 0.7), chunk(A1, 0.6)], {A1}),
        RetrievalCase("q3", "unanswerable_off_topic", [chunk(B1, 0.4)]),
    ]

    metrics = ranking_metrics(cases, ks=[1, 2])

    assert metrics.n == 2
    assert metrics.hit == {1: 0.5, 2: 1.0}
    assert metrics.recall == {1: 0.5, 2: 1.0}
    assert metrics.mrr == 0.75  # (1 + 1/2) / 2


def test_ranking_metrics_with_no_answerable_questions():
    assert ranking_metrics([RetrievalCase("q", "unanswerable_on_topic", [])], ks=[1]) is None


# --- threshold and top-k, mirroring retrieve() ---


def test_kept_chunks_mirrors_retrieve():
    ranking = [
        chunk(A1, 0.9, usable=False),
        chunk(A2, 0.8),
        chunk(A3, 0.5),
        chunk(B1, 0.7),  # beyond 2 * top_k: never searched for in the pipeline
    ]

    kept = kept_chunks(ranking, threshold=0.6, top_k=1)
    assert [c.page for c in kept] == [A2]
    kept = kept_chunks(ranking, threshold=0.6, top_k=2)
    assert [c.page for c in kept] == [A2, B1]
    assert kept_chunks(ranking, threshold=0.95, top_k=5) == []


CASES = [
    RetrievalCase("a1", "answerable", [chunk(A1, 0.70), chunk(B1, 0.60)], {A1}),
    RetrievalCase("a2", "answerable", [chunk(B1, 0.58), chunk(A2, 0.50)], {A2}),
    RetrievalCase("off", "unanswerable_off_topic", [chunk(B1, 0.45)]),
    RetrievalCase("on", "unanswerable_on_topic", [chunk(A3, 0.62)]),
]


def test_evaluate_cutoff():
    result = evaluate_cutoff(CASES, threshold=0.55, top_k=5)

    assert result.false_refusals == Rate(0, 2)
    assert result.expected_kept == Rate(1, 2)  # a2's expected page scores only 0.50
    assert result.false_answers_off_topic == Rate(0, 1)
    assert result.false_answers_on_topic == Rate(1, 1)
    assert result.mean_passages == (2 + 1 + 1) / 3


def test_threshold_sweep_trades_refusals_for_false_answers():
    low, high = threshold_sweep(CASES, [0.40, 0.65], top_k=5)

    assert (low.false_refusals, low.false_answers_off_topic) == (Rate(0, 2), Rate(1, 1))
    assert (high.false_refusals, high.false_answers_on_topic) == (Rate(1, 2), Rate(0, 1))


def test_top_k_sweep_changes_what_is_kept():
    one, two = top_k_sweep(CASES, threshold=0.0, top_ks=[1, 2])

    assert one.expected_kept == Rate(1, 2)
    assert two.expected_kept == Rate(2, 2)
    assert (one.mean_passages, two.mean_passages) == (1, 1.5)


# --- distributions ---


def test_distribution_interpolates_quartiles():
    d = distribution([0.4, 0.1, 0.3, 0.2, 0.5])
    assert (d.n, d.min, d.p25, d.median, d.p75, d.max) == (5, 0.1, 0.2, 0.3, 0.4, 0.5)
    single = distribution([0.7])
    assert (single.min, single.median, single.max) == (0.7, 0.7, 0.7)
    assert distribution([]) is None


def test_top_scores_by_type_uses_the_best_usable_score():
    diagram_first = [chunk(A1, 0.99, usable=False), chunk(A1, 0.3)]
    cases = CASES + [RetrievalCase("diagram", "answerable", diagram_first, {A1})]

    scores = top_scores_by_type(cases)

    assert scores["answerable"].max == 0.70  # the unusable 0.99 is ignored
    assert scores["answerable"].min == 0.3
    assert scores["unanswerable_on_topic"].median == 0.62


def test_alnum_sweep():
    chunks = [(0.95, True), (0.45, False), (0.55, True), (0.2, False)]

    low, high = alnum_sweep(chunks, [0.3, 0.6])

    assert (low.dropped, low.dropped_expected) == (Rate(1, 4), 0)
    assert (high.dropped, high.dropped_expected) == (Rate(3, 4), 1)


# --- answers ---


def test_refusal_metrics_split_by_type_and_layer():
    cases = [
        AnswerCase("off1", "unanswerable_off_topic", reason="no_relevant_chunks"),
        AnswerCase("off2", "unanswerable_off_topic", reason="ok"),
        AnswerCase("on1", "unanswerable_on_topic", reason="model_declined"),
        AnswerCase("a1", "answerable", reason="ok"),
        AnswerCase("a2", "answerable", reason="no_relevant_chunks"),
        AnswerCase("a3", "answerable", status="error"),  # a 503: not counted at all
    ]

    metrics = refusal_metrics(cases)

    assert metrics.correct_refusals == {
        "unanswerable_off_topic": Rate(1, 2),
        "unanswerable_on_topic": Rate(1, 1),
    }
    assert metrics.false_refusals == Rate(1, 2)
    assert metrics.reasons["answerable"] == {"no_relevant_chunks": 1, "ok": 1}
    assert metrics.reasons["unanswerable_on_topic"] == {"model_declined": 1}


def test_citation_metrics():
    cases = [
        AnswerCase("a1", "answerable", reason="ok", expected={A1}, cited=[A1, B1]),
        AnswerCase("a2", "follow_up", reason="ok", expected={A2}, cited=[A3]),
        AnswerCase("a3", "answerable", reason="ok", expected={A3}, cited=[]),
        AnswerCase("a4", "answerable", reason="model_declined", expected={A1}),  # refused
        AnswerCase("off", "unanswerable_off_topic", reason="ok", cited=[B1]),  # no expected pages
    ]

    metrics = citation_metrics(cases)

    assert metrics.answers == 3
    assert metrics.precision == Rate(1, 3)
    assert metrics.any_correct == Rate(1, 3)
    assert metrics.uncited == Rate(1, 3)


def test_faithfulness_metrics():
    cases = [
        AnswerCase("a1", "answerable", reason="ok", claims_supported=3, claims_total=3),
        AnswerCase("a2", "answerable", reason="ok", claims_supported=1, claims_total=2),
        AnswerCase("a3", "answerable", reason="ok"),  # not judged (e.g. --limit or judge error)
        AnswerCase("a4", "answerable", status="skipped"),
    ]

    metrics = faithfulness_metrics(cases)

    assert metrics.judged == 2
    assert metrics.claims == Rate(4, 5)
    assert metrics.fully_supported == Rate(1, 2)


def test_rewrite_metrics():
    cases = [
        AnswerCase(
            "f1", "follow_up", reason="ok", rewrite_fell_back=False, rewrite_same_meaning=True
        ),
        AnswerCase(
            "f2", "follow_up", reason="ok", rewrite_fell_back=False, rewrite_same_meaning=False
        ),
        AnswerCase("f3", "follow_up", reason="ok", rewrite_fell_back=True),  # nothing to judge
        AnswerCase("f4", "follow_up", status="error"),
        AnswerCase("a1", "answerable", reason="ok"),
    ]

    metrics = rewrite_metrics(cases)

    assert metrics.follow_ups == 3
    assert metrics.fell_back == Rate(1, 3)
    assert metrics.same_meaning == Rate(1, 2)


def test_status_counts():
    cases = [
        AnswerCase("a", "answerable"),
        AnswerCase("b", "answerable", status="error"),
        AnswerCase("c", "answerable", status="skipped"),
    ]
    assert status_counts(cases) == {"error": 1, "ok": 1, "skipped": 1}
