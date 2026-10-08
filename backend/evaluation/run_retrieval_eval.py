"""Retrieval evaluation: no LLM calls, so it is fast and free.

Every question is searched once with app.services.chat.retrieve (a large k, no
threshold); all metrics and sweeps are computed from those rankings. Follow-ups
are searched twice: as typed, and as the expected standalone question (what a
perfect rewrite would give).

Usage (from backend/):
    python -m evaluation.run_retrieval_eval [--documents DIR] [--out DIR] [--chunk-sweep]
"""

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from app.config import settings
from app.rag.text_quality import alnum_ratio, is_front_matter
from app.services.chat import retrieve
from evaluation.dataset import (
    DEFAULT_DATASET,
    DEFAULT_DOCUMENTS_DIR,
    EVAL_DIR,
    EvalDataset,
    EvalItem,
    load_dataset,
)
from evaluation.harness import EvalIndex, ensure_outside_data, temporary_index
from evaluation.metrics import (
    PageRef,
    RankedChunk,
    RankingMetrics,
    Rate,
    RetrievalCase,
    alnum_sweep,
    evaluate_cutoff,
    kept_chunks,
    ranking_metrics,
    threshold_sweep,
    top_k_sweep,
    top_scores_by_type,
)
from evaluation.report import num, pct, run_header, table

DEFAULT_OUT = EVAL_DIR / "results"  # git-ignored
KS = (1, 3, 5, 8, 10)  # 8 = the app's retrieval_top_k since Phase 9
THRESHOLDS = tuple(round(0.45 + 0.025 * i, 3) for i in range(11))  # 0.45 .. 0.70
TOP_KS = (1, 3, 5, 8, 10)
ALNUM_RATIOS = (0.3, 0.4, 0.5, 0.6, 0.7)
CHUNK_CONFIGS = ((1000, 150), (1800, 250), (2500, 350))  # (max_chars, overlap_chars)
# Enough results for every sweep: kept_chunks looks at the first 2 * top_k.
SEARCH_K = 2 * max(TOP_KS)
HISTOGRAM_BINS = tuple(round(0.30 + 0.05 * i, 2) for i in range(13))  # 0.30 .. 0.90


def rank(query: str, index: EvalIndex, search_k: int = SEARCH_K) -> list[RankedChunk]:
    """Search like the chat does (same function, all documents), but keep everything."""
    retrieval = retrieve(
        query,
        list(index.app_ids.values()),
        index.store,
        top_k=search_k // 2,  # retrieve searches 2 * top_k
        min_similarity=-1.0,  # no threshold: the sweeps apply their own
    )
    # The two filters are recorded separately (not through is_usable, which depends on
    # the exclude_front_matter setting), so every metric can be computed with the
    # front-matter filter off and on from this one search.
    return [
        RankedChunk(
            page=(index.dataset_ids[r.document_id], r.page),
            score=r.score,
            usable=alnum_ratio(r.text) >= settings.min_alnum_ratio,
            chunk_index=r.chunk_index,
            front_matter=is_front_matter(r.text),
        )
        for r in retrieval.results
    ]


def expected_pages(item: EvalItem) -> set[PageRef]:
    return {(item.document, p) for p in item.pages} if item.document else set()


def build_cases(
    dataset: EvalDataset, index: EvalIndex
) -> tuple[list[RetrievalCase], list[RetrievalCase]]:
    """Cases for the main metrics (follow-ups as their expected standalone question),
    and the follow-ups as typed, without any rewriting."""
    main_cases, raw_follow_ups = [], []
    for item in dataset.items:
        query = item.expected_standalone if item.type == "follow_up" else item.question
        main_cases.append(
            RetrievalCase(item.id, item.type, rank(query, index), expected_pages(item))
        )
        if item.type == "follow_up":
            raw_follow_ups.append(
                RetrievalCase(item.id, item.type, rank(item.question, index), expected_pages(item))
            )
    return main_cases, raw_follow_ups


def build_reworded_cases(dataset: EvalDataset, index: EvalIndex) -> list[RetrievalCase]:
    """The reworded tuning questions, searched as asked (they are all answerable)."""
    return [
        RetrievalCase(item.id, item.type, rank(item.question, index), expected_pages(item))
        for item in dataset.reworded_items()
    ]


@dataclass
class FlaggedChunk:
    """A chunk of the evaluation index that the front-matter rule flags."""

    document: str  # dataset document id
    page: int
    chunk_index: int
    on_tuning_page: bool  # on a page a tuning question expects (then dropping it could hurt)
    on_held_out_page: bool  # the same for the held-out questions (reported, never used to choose)
    start: str  # first 100 characters: for the git-ignored audit file only, never the report


@dataclass
class RemovedPassage:
    """A front-matter passage the model is given with the filter off, which the filter removes."""

    question_set: str
    item_id: str
    rank: int  # 1 = best search result
    page: PageRef
    chunk_index: int
    score: float


def flagged_chunks(dataset: EvalDataset, index: EvalIndex) -> list[FlaggedChunk]:
    """Every indexed chunk the front-matter rule flags, in document and page order."""
    tuning_pages = set().union(*(expected_pages(i) for i in dataset.tuning_items()))
    held_out = [i for i in dataset.items if i.id in dataset.held_out_ids()]
    held_out_pages = set().union(*(expected_pages(i) for i in held_out))
    return [
        FlaggedChunk(
            document=doc_id,
            page=c.page,
            chunk_index=c.chunk_index,
            on_tuning_page=(doc_id, c.page) in tuning_pages,
            on_held_out_page=(doc_id, c.page) in held_out_pages,
            start=" ".join(c.text.split())[:100],
        )
        for doc_id, app_id in index.app_ids.items()
        for c in index.store.get_chunks(app_id)
        if is_front_matter(c.text)
    ]


def removed_passages(question_sets: dict[str, Sequence[RetrievalCase]]) -> list[RemovedPassage]:
    """Front-matter passages kept at the current threshold and top_k with the filter off."""
    removed = []
    for label, cases in question_sets.items():
        for case in cases:
            kept = kept_chunks(case.ranking, settings.min_similarity, settings.retrieval_top_k)
            for chunk in kept:
                if chunk.front_matter:
                    removed.append(
                        RemovedPassage(
                            label, case.item_id, case.ranking.index(chunk) + 1,
                            chunk.page, chunk.chunk_index, chunk.score,
                        )
                    )
    return removed


def front_matter_comparison(question_sets: dict[str, Sequence[RetrievalCase]]) -> dict:
    """Each question set at the current threshold and top_k, with the filter off and on."""
    return {
        label: {
            ("on" if drop else "off"): {
                "ranking": ranking_metrics(cases, KS, drop_front_matter=drop),
                "cutoff": evaluate_cutoff(
                    cases, settings.min_similarity, settings.retrieval_top_k, drop_front_matter=drop
                ),
            }
            for drop in (False, True)
        }
        for label, cases in question_sets.items()
    }


def alnum_inputs(dataset: EvalDataset, index: EvalIndex) -> list[tuple[float, bool]]:
    """(alnum ratio, is on a page a tuning question expects) for every indexed chunk."""
    expected = set().union(*(expected_pages(i) for i in dataset.tuning_items()))
    return [
        (alnum_ratio(c.text), (doc_id, c.page) in expected)
        for doc_id, app_id in index.app_ids.items()
        for c in index.store.get_chunks(app_id)
    ]


def chunk_sweep(dataset: EvalDataset, documents_dir: Path) -> list[dict]:
    """Re-index into a fresh temporary store per chunk size and compare ranking quality."""
    rows = []
    for max_chars, overlap in CHUNK_CONFIGS:
        with temporary_index(
            dataset, documents_dir, max_chars=max_chars, overlap_chars=overlap
        ) as index:
            cases, _ = build_cases(dataset, index)
            chunks = sum(len(index.store.get_chunks(a)) for a in index.app_ids.values())
        cases = tuning_only(cases, dataset)  # chunk size is a setting: never chosen on held-out
        rows.append(
            {
                "max_chars": max_chars,
                "overlap_chars": overlap,
                "chunks": chunks,
                "ranking": ranking_metrics(cases, KS, settings.exclude_front_matter),
                "at_settings": evaluate_cutoff(
                    cases,
                    settings.min_similarity,
                    settings.retrieval_top_k,
                    settings.exclude_front_matter,
                ),
            }
        )
    return rows


def tuning_only(cases: Sequence[RetrievalCase], dataset: EvalDataset) -> list[RetrievalCase]:
    held_out_ids = dataset.held_out_ids()
    return [c for c in cases if c.item_id not in held_out_ids]


def held_out_only(cases: Sequence[RetrievalCase], dataset: EvalDataset) -> list[RetrievalCase]:
    held_out_ids = dataset.held_out_ids()
    return [c for c in cases if c.item_id in held_out_ids]


def _type_counts(cases: Sequence[RetrievalCase]) -> dict[str, int]:
    return {t: sum(c.type == t for c in cases) for t in sorted({c.type for c in cases})}


def evaluate(dataset: EvalDataset, documents_dir: Path, *, with_chunk_sweep: bool) -> dict:
    """Every sweep, distribution and "tuning set" row uses the tuning items only; the
    held-out items (owner-written) only appear in their own rows, so they never
    influence which setting looks best."""
    with temporary_index(dataset, documents_dir) as index:
        all_cases, raw_follow_ups = build_cases(dataset, index)
        reworded = build_reworded_cases(dataset, index)
        chunks = alnum_inputs(dataset, index)
        flagged = flagged_chunks(dataset, index)
    cases = tuning_only(all_cases, dataset)
    held_out = held_out_only(all_cases, dataset)
    raw_follow_ups = tuning_only(raw_follow_ups, dataset)
    standalone_follow_ups = [c for c in cases if c.type == "follow_up"]
    # Every row "at the current settings" follows the app's front-matter setting.
    fm = settings.exclude_front_matter
    question_sets = {"tuning": cases, "reworded": reworded, "held-out": held_out}
    return {
        "cases": cases,
        "held_out_cases": held_out,
        "reworded_cases": reworded,
        "counts": _type_counts(cases),
        "held_out_counts": _type_counts(held_out),
        "ranking": ranking_metrics(cases, KS, fm),
        "ranking_held_out": ranking_metrics(held_out, KS, fm),
        "ranking_reworded": ranking_metrics(reworded, KS, fm),
        "follow_ups_raw": ranking_metrics(raw_follow_ups, KS, fm),
        "follow_ups_standalone": ranking_metrics(standalone_follow_ups, KS, fm),
        "top_scores": top_scores_by_type(cases),
        "top_scores_held_out": top_scores_by_type(held_out),
        "threshold_sweep": threshold_sweep(cases, THRESHOLDS, settings.retrieval_top_k, fm),
        "top_k_sweep": top_k_sweep(cases, settings.min_similarity, TOP_KS, fm),
        "at_settings_held_out": evaluate_cutoff(
            held_out, settings.min_similarity, settings.retrieval_top_k, fm
        ),
        "alnum_sweep": alnum_sweep(chunks, ALNUM_RATIOS),
        "chunk_sweep": chunk_sweep(dataset, documents_dir) if with_chunk_sweep else None,
        "front_matter": front_matter_comparison(question_sets),
        "front_matter_flagged": flagged,
        "front_matter_removed": removed_passages(question_sets),
    }


# --- Report ---


def _ranking_rows(label: str, m) -> list[list[object]]:
    if m is None:
        return [[label, 0] + ["–"] * (2 * len(KS) + 1)]
    return [
        [label, m.n]
        + [num(m.hit[k], 2) for k in KS]
        + [num(m.recall[k], 2) for k in KS]
        + [num(m.mrr, 2)]
    ]


RANKING_HEADERS = (
    ["Questions", "n"] + [f"hit@{k}" for k in KS] + [f"recall@{k}" for k in KS] + ["MRR"]
)


def _cutoff_rows(results: Sequence, key: str) -> list[list[object]]:
    return [
        [
            getattr(r, key),
            pct(r.false_refusals),
            pct(r.expected_kept),
            pct(r.false_answers_off_topic),
            pct(r.false_answers_on_topic),
            num(r.mean_passages, 1),
        ]
        for r in results
    ]


CUTOFF_COLUMNS = [
    "false refusals (answerable)",
    "expected page kept (answerable)",
    "reach LLM: off-topic",
    "reach LLM: on-topic unanswerable",
    "mean passages",
]


def _distribution_table(distributions: dict) -> list[str]:
    return table(
        ["Type", "n", "min", "p25", "median", "p75", "max"],
        [
            [t, d.n, num(d.min), num(d.p25), num(d.median), num(d.p75), num(d.max)]
            for t, d in distributions.items()
        ],
    )


def _histogram(cases: Sequence[RetrievalCase]) -> list[str]:
    """Counts of each question's best usable score per bin, as a text table with bars."""
    groups = {
        "answerable": ("answerable", "follow_up"),
        "off-topic": ("unanswerable_off_topic",),
        "on-topic unanswerable": ("unanswerable_on_topic",),
    }
    best = {
        c.item_id: next((r.score for r in c.ranking if r.usable), None) for c in cases
    }
    rows = []
    for low, high in zip(HISTOGRAM_BINS, HISTOGRAM_BINS[1:]):
        row = [f"{low:.2f}–{high:.2f}"]
        for types in groups.values():
            n = sum(
                1 for c in cases
                if c.type in types and best[c.item_id] is not None and low <= best[c.item_id] < high
            )
            row.append(("█" * n + f" {n}") if n else "")
        rows.append(row)
    return table(["best score"] + list(groups), rows)


def render(result: dict, dataset: EvalDataset) -> str:
    lines = run_header("Retrieval evaluation")
    tuning = ", ".join(f"{t}: {n}" for t, n in result["counts"].items())
    held_out_text = ", ".join(f"{t}: {n}" for t, n in result["held_out_counts"].items())
    lines += [
        f"Dataset: {len(dataset.items)} questions. Tuning set: {len(result['cases'])} ({tuning}). "
        f"Held-out set, written by the project owner: {len(result['held_out_cases'])} "
        f"({held_out_text or 'none'}).",
        "",
        "**Read with care.** Every sweep, score distribution and \"tuning set\" row uses only "
        "the tuning set, and settings are chosen from those, so the numbers at a chosen setting "
        "are optimistic. The held-out questions are never used to choose settings; they appear "
        "only in the held-out rows and give the unbiased check. Every percentage shows its "
        "counts: with this few questions, one question moves a rate by several points.",
        "",
        "Relevance is per page: a chunk counts if its page is one of the item's expected pages. "
        "Follow-ups are searched as their expected standalone question (a perfect rewrite) "
        "unless stated otherwise.",
        "",
        "## Ranking quality (no threshold)",
        "",
        "Answerable questions and follow-ups only; unusable (diagram) chunks are skipped, "
        "as in the chat.",
        "",
    ]
    rows = _ranking_rows("all (tuning set)", result["ranking"])
    rows += _ranking_rows("reworded tuning questions", result["ranking_reworded"])
    rows += _ranking_rows("held-out (owner-written)", result["ranking_held_out"])
    rows += _ranking_rows("follow-ups as typed", result["follow_ups_raw"])
    rows += _ranking_rows("follow-ups, expected standalone", result["follow_ups_standalone"])
    lines += table(RANKING_HEADERS, rows)

    lines += ["## Best score per question (tuning set)", ""]
    lines += _distribution_table(result["top_scores"])
    lines += _histogram(result["cases"])
    lines += ["Held-out set:", ""]
    lines += _distribution_table(result["top_scores_held_out"])

    lines += [
        f"## min_similarity sweep (tuning set, top_k = {settings.retrieval_top_k})",
        "",
        "What the retrieval layer alone does. A question that reaches the LLM can still be "
        "declined by the model, so 'reach LLM' is an upper bound on false answers.",
        "",
    ]
    sweep = _cutoff_rows(result["threshold_sweep"], "threshold")
    lines += table(["min_similarity"] + CUTOFF_COLUMNS, sweep)
    lines += [
        f"## retrieval_top_k sweep (tuning set, min_similarity = {settings.min_similarity})",
        "",
    ]
    lines += table(["top_k"] + CUTOFF_COLUMNS, _cutoff_rows(result["top_k_sweep"], "top_k"))
    lines += ["Held-out set at the current settings (not used to choose them):", ""]
    held_out = _cutoff_rows([result["at_settings_held_out"]], "threshold")
    lines += table(["min_similarity"] + CUTOFF_COLUMNS, held_out)

    lines += ["## min_alnum_ratio", "", "Chunks the diagram filter would drop at each ratio.", ""]
    lines += table(
        ["min_alnum_ratio", "chunks dropped", "of which on a page a tuning question expects"],
        [[r.min_ratio, pct(r.dropped), r.dropped_expected] for r in result["alnum_sweep"]],
    )

    if result["chunk_sweep"]:
        lines += [
            "## Chunk size (tuning set)",
            "",
            "Each size re-indexed into its own temporary store.",
            "",
        ]
        rows = []
        for row in result["chunk_sweep"]:
            m, cut = row["ranking"], row["at_settings"]
            rows.append(
                [row["max_chars"], row["overlap_chars"], row["chunks"]]
                + [pct(_hit_rate(m, k)) for k in (1, 5)]
                + [num(m.mrr, 2), pct(cut.false_refusals), pct(cut.false_answers_on_topic)]
            )
        lines += table(
            ["max_chars", "overlap", "chunks", "hit@1", "hit@5", "MRR",
             "false refusals", "reach LLM: on-topic"],
            rows,
        )
    lines += _front_matter_section(result)
    return "\n".join(lines)


SET_LABELS = {"tuning": "Tuning", "reworded": "Reworded", "held-out": "Held-out"}


def _front_matter_section(result: dict) -> list[str]:
    """Filter off vs on for each question set, then which chunks it flags and removes.

    Pages and scores only: the committed reports never contain document text.
    """
    comparison = result["front_matter"]
    lines = [
        "## Front-matter filter (Phase 9)",
        "",
        f"At min_similarity {settings.min_similarity} and top_k {settings.retrieval_top_k}, "
        "computed from the same searches with the filter off and on. Tuning: the original "
        "tuning questions (follow-ups as their expected standalone question). Reworded: the "
        "same answerable tuning questions in other words. Held-out: reported only, never used "
        "to choose. App setting during this run: exclude_front_matter = "
        f"{settings.exclude_front_matter}.",
        "",
    ]
    headers = ["Metric"] + [
        f"{SET_LABELS[label]} {state}" for label in comparison for state in ("off", "on")
    ]

    def row(name: str, value) -> list[object]:
        return [name] + [
            value(comparison[label][state]) for label in comparison for state in ("off", "on")
        ]

    def hit(k: int):
        return lambda r: pct(_hit_rate(r["ranking"], k)) if r["ranking"] else "–"

    def cutoff(field: str):
        return lambda r: pct(getattr(r["cutoff"], field))

    rows = [
        row("hit@8 (usable ranking)", hit(8)),
        row("hit@5 (usable ranking)", hit(5)),
        row("expected page kept", cutoff("expected_kept")),
        row("false refusals (retrieval)", cutoff("false_refusals")),
        row("front-matter slots / kept slots", cutoff("front_matter_slots")),
        row("questions with ≥1 front-matter slot", cutoff("questions_with_front_matter")),
        row("mean passages", lambda r: num(r["cutoff"].mean_passages, 2)),
        row("reach LLM: off-topic", cutoff("false_answers_off_topic")),
        row("reach LLM: on-topic unanswerable", cutoff("false_answers_on_topic")),
    ]
    lines += table(headers, rows)

    flagged = result["front_matter_flagged"]
    per_doc = {}
    for f in flagged:
        per_doc.setdefault(f.document, []).append(f)
    lines += [
        "### Chunks the rule flags (whole evaluation index)",
        "",
        f"{len(flagged)} chunks flagged; on a page a tuning question expects: "
        f"{sum(f.on_tuning_page for f in flagged)}; on a held-out expected page: "
        f"{sum(f.on_held_out_page for f in flagged)}.",
        "",
    ]
    lines += table(
        ["Document", "flagged", "pages"],
        [[doc, len(fs), ", ".join(str(f.page) for f in fs)] for doc, fs in per_doc.items()],
    )
    removed = result["front_matter_removed"]
    lines += [
        "### Front-matter passages the filter removes",
        "",
        "Passages the model is given with the filter off (at the settings above).",
        "",
    ]
    lines += table(
        ["Set", "Question", "rank", "page", "chunk", "score"],
        [
            [SET_LABELS[r.question_set], r.item_id, r.rank, f"{r.page[0]} p{r.page[1]}",
             r.chunk_index, num(r.score)]
            for r in removed
        ],
    ) if removed else ["None.", ""]
    return lines


def render_audit(result: dict) -> str:
    """The flagged-chunk audit with the start of each chunk's text, for a person to read.

    Written to the git-ignored results folder only: it contains document text.
    """
    flagged = result["front_matter_flagged"]
    starts = {(f.document, f.chunk_index): f.start for f in flagged}
    lines = [
        "# Front-matter audit (contains document text: do not commit)",
        "",
        f"## Every flagged chunk ({len(flagged)})",
        "",
    ]
    lines += table(
        ["Document", "page", "chunk", "tuning page", "held-out page", "first 100 characters"],
        [
            [f.document, f.page, f.chunk_index, "YES" if f.on_tuning_page else "",
             "YES" if f.on_held_out_page else "", f.start.replace("|", "/")]
            for f in flagged
        ],
    )
    lines += ["## Removed from what the model is given", ""]
    lines += table(
        ["Set", "Question", "rank", "page", "score", "first 100 characters"],
        [
            [SET_LABELS[r.question_set], r.item_id, r.rank, f"{r.page[0]} p{r.page[1]}",
             num(r.score), starts[(r.page[0], r.chunk_index)].replace("|", "/")]
            for r in result["front_matter_removed"]
        ],
    )
    return "\n".join(lines)


def _hit_rate(m: RankingMetrics, k: int) -> Rate:
    """hit@k as a count out of n. The stored hit rate is a mean of one 0/1 per question,
    so rate * n is a whole number; round() only removes floating-point fuzz."""
    return Rate(round(m.hit[k] * m.n), m.n)


def to_json(result: dict) -> str:
    """Everything as JSON; rankings are trimmed to the top 10 and hold no chunk text."""
    case_keys = ("cases", "held_out_cases", "reworded_cases")
    data = {k: v for k, v in result.items() if k not in case_keys}
    # No document text in the JSON either: drop the start of each flagged chunk.
    data["front_matter_flagged"] = [
        {k: v for k, v in asdict(f).items() if k != "start"} for f in result["front_matter_flagged"]
    ]
    for key in case_keys:
        data[key] = [
            {
                **asdict(c),
                "expected": sorted(c.expected),
                "ranking": [asdict(r) for r in c.ranking[:10]],
            }
            for c in result[key]
        ]
    return json.dumps(data, default=_json_default, indent=1, ensure_ascii=False)


def _json_default(value):
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    if isinstance(value, set):
        return sorted(value)
    raise TypeError(f"can't serialise {type(value).__name__}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Retrieval evaluation (no LLM).")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--documents", type=Path, default=DEFAULT_DOCUMENTS_DIR)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--chunk-sweep", action="store_true", help="re-index per chunk size (slow)")
    args = parser.parse_args(argv)

    out = ensure_outside_data(args.out)
    dataset = load_dataset(args.dataset)
    result = evaluate(dataset, args.documents, with_chunk_sweep=args.chunk_sweep)

    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    (out / f"retrieval-{stamp}.json").write_text(to_json(result), encoding="utf-8")
    report = out / "retrieval-report.md"
    report.write_text(render(result, dataset), encoding="utf-8")
    audit = out / "front-matter-audit.md"
    audit.write_text(render_audit(result), encoding="utf-8")
    print(f"Report: {report}\nFront-matter audit (has document text, don't commit): {audit}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
