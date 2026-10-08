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
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from app.config import settings
from app.rag.text_quality import alnum_ratio
from app.services.chat import retrieve
from app.services.selection import is_usable
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
    ranking_metrics,
    threshold_sweep,
    top_k_sweep,
    top_scores_by_type,
)
from evaluation.report import num, pct, run_header, table

DEFAULT_OUT = EVAL_DIR / "results"  # git-ignored
KS = (1, 3, 5, 10)
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
    return [
        RankedChunk(
            page=(index.dataset_ids[r.document_id], r.page),
            score=r.score,
            usable=is_usable(r.text),
            chunk_index=r.chunk_index,
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


def alnum_inputs(dataset: EvalDataset, index: EvalIndex) -> list[tuple[float, bool]]:
    """(alnum ratio, is on an expected page) for every indexed chunk."""
    expected = set().union(*(expected_pages(i) for i in dataset.items))
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
        rows.append(
            {
                "max_chars": max_chars,
                "overlap_chars": overlap,
                "chunks": chunks,
                "ranking": ranking_metrics(cases, KS),
                "at_settings": evaluate_cutoff(
                    cases, settings.min_similarity, settings.retrieval_top_k
                ),
            }
        )
    return rows


def evaluate(dataset: EvalDataset, documents_dir: Path, *, with_chunk_sweep: bool) -> dict:
    with temporary_index(dataset, documents_dir) as index:
        cases, raw_follow_ups = build_cases(dataset, index)
        chunks = alnum_inputs(dataset, index)
    held_out_ids = {i.id for i in dataset.items if i.author == "user"}
    held_out = [c for c in cases if c.item_id in held_out_ids]
    standalone_follow_ups = [c for c in cases if c.type == "follow_up"]
    return {
        "cases": cases,
        "counts": {t: sum(c.type == t for c in cases) for t in sorted({c.type for c in cases})},
        "held_out_count": len(held_out),
        "ranking": ranking_metrics(cases, KS),
        "ranking_held_out": ranking_metrics(held_out, KS),
        "follow_ups_raw": ranking_metrics(raw_follow_ups, KS),
        "follow_ups_standalone": ranking_metrics(standalone_follow_ups, KS),
        "top_scores": top_scores_by_type(cases),
        "threshold_sweep": threshold_sweep(cases, THRESHOLDS, settings.retrieval_top_k),
        "top_k_sweep": top_k_sweep(cases, settings.min_similarity, TOP_KS),
        "at_settings_held_out": evaluate_cutoff(
            held_out, settings.min_similarity, settings.retrieval_top_k
        ),
        "alnum_sweep": alnum_sweep(chunks, ALNUM_RATIOS),
        "chunk_sweep": chunk_sweep(dataset, documents_dir) if with_chunk_sweep else None,
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
    counts = ", ".join(f"{t}: {n}" for t, n in result["counts"].items())
    lines += [
        f"Dataset: {len(dataset.items)} questions ({counts}); "
        f"{result['held_out_count']} written by the project owner (held-out).",
        "",
        "**Read with care.** The thresholds and top-k values below are tuned and reported on "
        "the same questions, so the numbers at a chosen setting are optimistic. Only the "
        "held-out questions (written by the project owner, not used to pick settings) give an "
        "unbiased check. Every percentage shows its counts: with this few questions, one "
        "question moves a rate by several points.",
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
    rows += _ranking_rows("held-out (owner-written)", result["ranking_held_out"])
    rows += _ranking_rows("follow-ups as typed", result["follow_ups_raw"])
    rows += _ranking_rows("follow-ups, expected standalone", result["follow_ups_standalone"])
    lines += table(RANKING_HEADERS, rows)

    lines += ["## Best score per question", ""]
    lines += table(
        ["Type", "n", "min", "p25", "median", "p75", "max"],
        [
            [t, d.n, num(d.min), num(d.p25), num(d.median), num(d.p75), num(d.max)]
            for t, d in result["top_scores"].items()
        ],
    )
    lines += _histogram(result["cases"])

    lines += [
        f"## min_similarity sweep (top_k = {settings.retrieval_top_k})",
        "",
        "What the retrieval layer alone does. A question that reaches the LLM can still be "
        "declined by the model, so 'reach LLM' is an upper bound on false answers.",
        "",
    ]
    sweep = _cutoff_rows(result["threshold_sweep"], "threshold")
    lines += table(["min_similarity"] + CUTOFF_COLUMNS, sweep)
    lines += [f"## retrieval_top_k sweep (min_similarity = {settings.min_similarity})", ""]
    lines += table(["top_k"] + CUTOFF_COLUMNS, _cutoff_rows(result["top_k_sweep"], "top_k"))
    lines += ["Held-out questions at the current settings:", ""]
    held_out = _cutoff_rows([result["at_settings_held_out"]], "threshold")
    lines += table(["min_similarity"] + CUTOFF_COLUMNS, held_out)

    lines += ["## min_alnum_ratio", "", "Chunks the diagram filter would drop at each ratio.", ""]
    lines += table(
        ["min_alnum_ratio", "chunks dropped", "of which on an expected page"],
        [[r.min_ratio, pct(r.dropped), r.dropped_expected] for r in result["alnum_sweep"]],
    )

    if result["chunk_sweep"]:
        lines += ["## Chunk size", "", "Each size re-indexed into its own temporary store.", ""]
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
    return "\n".join(lines)


def _hit_rate(m: RankingMetrics, k: int) -> Rate:
    """hit@k as a count out of n. The stored hit rate is a mean of one 0/1 per question,
    so rate * n is a whole number; round() only removes floating-point fuzz."""
    return Rate(round(m.hit[k] * m.n), m.n)


def to_json(result: dict) -> str:
    """Everything as JSON; rankings are trimmed to the top 10 and hold no chunk text."""
    data = {k: v for k, v in result.items() if k != "cases"}
    data["cases"] = [
        {
            **asdict(c),
            "expected": sorted(c.expected),
            "ranking": [asdict(r) for r in c.ranking[:10]],
        }
        for c in result["cases"]
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
    print(f"Report: {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
