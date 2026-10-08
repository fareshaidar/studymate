"""Evaluation metrics as pure functions: no I/O, no LLM, no vector store.

The runners turn search results and chat results into the small records below;
everything here is plain counting, so it can be tested with hand-made examples.

Relevance is judged per page: a retrieved chunk is relevant if its (document, page)
is one of the item's expected pages. Chunks never cross pages, so this is exact.
"""

import statistics
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

PageRef = tuple[str, int]  # (dataset document id, page number)

HAS_ANSWER = ("answerable", "follow_up")
UNANSWERABLE = ("unanswerable_off_topic", "unanswerable_on_topic")


@dataclass(frozen=True)
class Rate:
    """`count` out of `total`, kept as counts so reports can show the n behind a percentage."""

    count: int
    total: int

    @property
    def value(self) -> float | None:
        return self.count / self.total if self.total else None


def rate(flags: Iterable[bool]) -> Rate:
    flags = list(flags)
    return Rate(sum(flags), len(flags))


def mean(values: Iterable[float]) -> float | None:
    values = list(values)
    return sum(values) / len(values) if values else None


# --- Retrieval ---


@dataclass(frozen=True)
class RankedChunk:
    """One search result, best first, reduced to what the metrics need."""

    page: PageRef
    score: float
    usable: bool  # passes the diagram filter (is_usable), like in the chat pipeline
    chunk_index: int = 0  # identifies the chunk within its document (for drift checks)


@dataclass
class RetrievalCase:
    """One question and everything its search returned (a large k, before any filtering)."""

    item_id: str
    type: str
    ranking: list[RankedChunk]
    expected: set[PageRef] = field(default_factory=set)  # empty for unanswerable items

    @property
    def has_answer(self) -> bool:
        return self.type in HAS_ANSWER


def usable_pages(ranking: Sequence[RankedChunk]) -> list[PageRef]:
    """The pages of the usable chunks, best first: what the model could ever be shown."""
    return [c.page for c in ranking if c.usable]


def hit_at_k(pages: Sequence[PageRef], expected: set[PageRef], k: int) -> bool:
    """Is any expected page among the first k results?"""
    return any(p in expected for p in pages[:k])


def recall_at_k(pages: Sequence[PageRef], expected: set[PageRef], k: int) -> float:
    """Share of the expected pages that appear among the first k results.

    Matters when an answer is spread over several pages; for one expected page
    it equals hit@k.
    """
    if not expected:
        raise ValueError("recall needs at least one expected page")
    return len(expected & set(pages[:k])) / len(expected)


def reciprocal_rank(pages: Sequence[PageRef], expected: set[PageRef]) -> float:
    """1 / rank of the first relevant result (rank 1 = best), or 0 if there is none."""
    for rank, page in enumerate(pages, start=1):
        if page in expected:
            return 1 / rank
    return 0.0


@dataclass
class RankingMetrics:
    n: int
    hit: dict[int, float]  # k -> hit rate
    recall: dict[int, float]  # k -> mean recall
    mrr: float


def ranking_metrics(cases: Sequence[RetrievalCase], ks: Sequence[int]) -> RankingMetrics | None:
    """Hit rate, recall and MRR over the usable ranking, no threshold (pure ranking quality)."""
    cases = [c for c in cases if c.has_answer]
    if not cases:
        return None
    rankings = [(usable_pages(c.ranking), c.expected) for c in cases]
    return RankingMetrics(
        n=len(cases),
        hit={k: mean(hit_at_k(p, e, k) for p, e in rankings) for k in ks},
        recall={k: mean(recall_at_k(p, e, k) for p, e in rankings) for k in ks},
        mrr=mean(reciprocal_rank(p, e) for p, e in rankings),
    )


def kept_chunks(ranking: Sequence[RankedChunk], threshold: float, top_k: int) -> list[RankedChunk]:
    """What the chat pipeline would give the model, mirroring app.services.chat.retrieve:
    search 2 * top_k, keep usable chunks scoring at least `threshold`, at most top_k of them.
    """
    return [c for c in ranking[: top_k * 2] if c.usable and c.score >= threshold][:top_k]


@dataclass
class Distribution:
    n: int
    min: float
    p25: float
    median: float
    p75: float
    max: float


def distribution(values: Iterable[float]) -> Distribution | None:
    values = sorted(values)
    if not values:
        return None
    if len(values) == 1:
        p25 = median = p75 = values[0]
    else:
        # "inclusive" interpolates between data points, like numpy's default percentile.
        p25, median, p75 = statistics.quantiles(values, n=4, method="inclusive")
    return Distribution(len(values), values[0], p25, median, p75, values[-1])


def top_scores_by_type(cases: Sequence[RetrievalCase]) -> dict[str, Distribution]:
    """Distribution of each question's best usable score, per question type.

    If answerable and unanswerable questions overlap a lot here, no threshold can
    separate them well.
    """
    by_type: dict[str, list[float]] = {}
    for case in cases:
        best = next((c.score for c in case.ranking if c.usable), None)
        if best is not None:
            by_type.setdefault(case.type, []).append(best)
    return {t: distribution(scores) for t, scores in sorted(by_type.items())}


@dataclass
class CutoffResult:
    """What the retrieval layer alone does at one (threshold, top_k) setting."""

    threshold: float
    top_k: int
    false_refusals: Rate  # answerable questions where nothing was kept
    expected_kept: Rate  # answerable questions where an expected page was kept
    false_answers_off_topic: Rate  # off-topic questions that would reach the LLM
    false_answers_on_topic: Rate  # on-topic unanswerable questions that would reach the LLM
    mean_passages: float | None  # passages sent to the LLM when not refused (cost)


def evaluate_cutoff(cases: Sequence[RetrievalCase], threshold: float, top_k: int) -> CutoffResult:
    kept = {c.item_id: kept_chunks(c.ranking, threshold, top_k) for c in cases}
    answerable = [c for c in cases if c.has_answer]

    def false_answers(question_type: str) -> Rate:
        return rate(bool(kept[c.item_id]) for c in cases if c.type == question_type)

    return CutoffResult(
        threshold=threshold,
        top_k=top_k,
        false_refusals=rate(not kept[c.item_id] for c in answerable),
        expected_kept=rate(any(k.page in c.expected for k in kept[c.item_id]) for c in answerable),
        false_answers_off_topic=false_answers("unanswerable_off_topic"),
        false_answers_on_topic=false_answers("unanswerable_on_topic"),
        mean_passages=mean(len(k) for k in kept.values() if k),
    )


def threshold_sweep(
    cases: Sequence[RetrievalCase], thresholds: Sequence[float], top_k: int
) -> list[CutoffResult]:
    return [evaluate_cutoff(cases, t, top_k) for t in thresholds]


def top_k_sweep(
    cases: Sequence[RetrievalCase], threshold: float, top_ks: Sequence[int]
) -> list[CutoffResult]:
    return [evaluate_cutoff(cases, threshold, k) for k in top_ks]


@dataclass
class AlnumRow:
    min_ratio: float
    dropped: Rate  # chunks that would be filtered out, of all chunks
    dropped_expected: int  # of those, chunks on a page some question expects


def alnum_sweep(
    chunks: Sequence[tuple[float, bool]], ratios: Sequence[float]
) -> list[AlnumRow]:
    """For each candidate min_alnum_ratio: how many chunks it would drop.

    `chunks` holds (alnum ratio, is on an expected page) per indexed chunk. Dropping
    a chunk on an expected page can turn an answerable question into a refusal.
    """
    return [
        AlnumRow(
            min_ratio=r,
            dropped=rate(ratio < r for ratio, _ in chunks),
            dropped_expected=sum(ratio < r and expected for ratio, expected in chunks),
        )
        for r in ratios
    ]


# --- Answers ---


@dataclass
class AnswerCase:
    """The outcome of one question through the full chat pipeline (and the judge).

    `status` is "ok" when the pipeline gave a result. "error" (the LLM kept failing,
    e.g. 503s) and "skipped" (call budget used up) are left out of every metric,
    so a service outage never counts as a wrong answer.
    """

    item_id: str
    type: str
    status: str = "ok"
    reason: str | None = None  # ok / no_relevant_chunks / model_declined
    expected: set[PageRef] = field(default_factory=set)
    cited: list[PageRef] = field(default_factory=list)  # page of every cited source
    claims_supported: int | None = None  # from the judge; None if not judged
    claims_total: int | None = None
    rewrite_fell_back: bool | None = None  # follow-ups: no usable rewrite, original used
    rewrite_same_meaning: bool | None = None  # follow-ups: judge's verdict on the rewrite

    @property
    def refused(self) -> bool:
        return self.reason != "ok"


def completed(cases: Iterable[AnswerCase]) -> list[AnswerCase]:
    return [c for c in cases if c.status == "ok"]


@dataclass
class RefusalMetrics:
    correct_refusals: dict[str, Rate]  # per unanswerable type
    false_refusals: Rate  # answerable questions that were refused
    # Which layer refused, per question type: reason -> count (incl. "ok" = not refused)
    reasons: dict[str, dict[str, int]]


def refusal_metrics(cases: Sequence[AnswerCase]) -> RefusalMetrics:
    cases = completed(cases)
    reasons: dict[str, Counter] = {}
    for c in cases:
        reasons.setdefault(c.type, Counter())[c.reason or "none"] += 1
    return RefusalMetrics(
        correct_refusals={
            t: rate(c.refused for c in cases if c.type == t)
            for t in UNANSWERABLE
            if any(c.type == t for c in cases)
        },
        false_refusals=rate(c.refused for c in cases if c.type in HAS_ANSWER),
        reasons={t: dict(sorted(counter.items())) for t, counter in sorted(reasons.items())},
    )


@dataclass
class CitationMetrics:
    answers: int  # answered questions that have expected pages
    precision: Rate  # cited sources on an expected page, of all cited sources
    any_correct: Rate  # answers with at least one citation on an expected page
    uncited: Rate  # answers with no citation at all


def citation_metrics(cases: Sequence[AnswerCase]) -> CitationMetrics:
    answered = [c for c in completed(cases) if c.type in HAS_ANSWER and not c.refused]
    cited = [(page, c.expected) for c in answered for page in c.cited]
    return CitationMetrics(
        answers=len(answered),
        precision=rate(page in expected for page, expected in cited),
        any_correct=rate(any(p in c.expected for p in c.cited) for c in answered),
        uncited=rate(not c.cited for c in answered),
    )


@dataclass
class FaithfulnessMetrics:
    judged: int  # answers the judge scored
    claims: Rate  # supported claims, of all claims
    fully_supported: Rate  # answers where every claim was supported


def faithfulness_metrics(cases: Sequence[AnswerCase]) -> FaithfulnessMetrics:
    judged = [c for c in completed(cases) if c.claims_total is not None]
    return FaithfulnessMetrics(
        judged=len(judged),
        claims=Rate(
            sum(c.claims_supported or 0 for c in judged), sum(c.claims_total for c in judged)
        ),
        fully_supported=rate(c.claims_supported == c.claims_total for c in judged),
    )


@dataclass
class RewriteMetrics:
    follow_ups: int
    fell_back: Rate  # the rewrite was unusable or failed, so the original question was used
    same_meaning: Rate  # of the rewrites the judge checked, those meaning the expected question


def rewrite_metrics(cases: Sequence[AnswerCase]) -> RewriteMetrics:
    follow_ups = [c for c in completed(cases) if c.type == "follow_up"]
    return RewriteMetrics(
        follow_ups=len(follow_ups),
        fell_back=rate(bool(c.rewrite_fell_back) for c in follow_ups),
        same_meaning=rate(
            c.rewrite_same_meaning for c in follow_ups if c.rewrite_same_meaning is not None
        ),
    )


def status_counts(cases: Iterable[AnswerCase]) -> dict[str, int]:
    """How many cases were ok, errors or skipped, for the report's footnote."""
    return dict(sorted(Counter(c.status for c in cases).items()))
