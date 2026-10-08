"""Answer evaluation: runs questions through the real chat pipeline, then an LLM judge.

Uses the LLM, so it is limited: one --max-calls budget (default 100) shared by the
answerer and the judge, about a second between real calls, a reply cache (a rerun
or a stopped run only pays for new prompts) and --limit N. Transient errors (429,
503) are retried later and, if they persist, recorded as errors, never as wrong answers.

Modes: real Gemini (default), --fake-llm (scripted, no key), --no-llm (retrieval-layer
refusals only, no LLM client at all).

Usage (from backend/):
    python -m evaluation.run_answer_eval [--limit N] [--max-calls N] [--fake-llm | --no-llm]
"""

import argparse
import json
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from app.llm.base import LLMClient
from app.rag.prompts import HistoryMessage
from app.rag.structured import generate_json
from app.services.chat import ChatResult, answer_question, retrieve
from evaluation.dataset import (
    DEFAULT_DATASET,
    DEFAULT_DOCUMENTS_DIR,
    EvalDataset,
    EvalItem,
    load_dataset,
)
from evaluation.harness import (
    DEFAULT_CACHE,
    CachedLLM,
    EvalIndex,
    StopRun,
    ensure_outside_data,
    make_llms,
    run_case,
    temporary_index,
)
from evaluation.judge_prompts import (
    FAITHFULNESS_SYSTEM_PROMPT,
    REWRITE_JUDGE_SYSTEM_PROMPT,
    FaithfulnessVerdict,
    RewriteVerdict,
    build_faithfulness_prompt,
    build_rewrite_judge_prompt,
)
from evaluation.metrics import (
    AnswerCase,
    Rate,
    citation_metrics,
    faithfulness_metrics,
    hit_at_k,
    rate,
    refusal_metrics,
    rewrite_metrics,
    status_counts,
    usable_pages,
)
from evaluation.report import pct, run_header, table
from evaluation.run_retrieval_eval import DEFAULT_OUT, expected_pages, rank

TYPE_ORDER = ("answerable", "follow_up", "unanswerable_off_topic", "unanswerable_on_topic")


@dataclass
class ItemRecord:
    """One item's outcome: the metrics' AnswerCase plus what a human may want to inspect."""

    case: AnswerCase
    author: str
    error: str | None = None  # error class name when status is "error"
    answer: str | None = None
    rewritten_question: str | None = None
    judge_error: str | None = None  # the judge failed; the answer still counts elsewhere
    rewrite_hit_at_5: bool | None = None
    note: str | None = None  # e.g. why the item was skipped


@dataclass
class RunSummary:
    mode: str
    judge_model: str | None
    records: list[ItemRecord] = field(default_factory=list)
    stopped: str | None = None  # why the run stopped early, if it did
    real_calls: int = 0
    cache_hits: int = 0


def round_robin(items: Sequence[EvalItem]) -> list[EvalItem]:
    """Interleave the types, so `--limit 20` still covers every type of question."""
    groups = [[i for i in items if i.type == t] for t in TYPE_ORDER]
    ordered = []
    while any(groups):
        for group in groups:
            if group:
                ordered.append(group.pop(0))
    return ordered


def _history(item: EvalItem) -> list[HistoryMessage]:
    return [HistoryMessage(t.role, t.content) for t in item.history]


def answer_item(
    item: EvalItem,
    index: EvalIndex,
    answerer: LLMClient,
    judge: LLMClient,
    sleep: Callable[[float], None],
) -> ItemRecord:
    """Ask one question through the chat pipeline, then judge the answer (and the rewrite).

    Raises StopRun if the answer itself can't be attempted; a StopRun during judging
    keeps the answer and only leaves the judgement out.
    """
    expected = expected_pages(item)
    outcome = run_case(
        lambda: answer_question(
            item.question,
            None,
            session=index.session,
            store=index.store,
            llm=answerer,
            history=_history(item),
        ),
        sleep=sleep,
    )
    case = AnswerCase(item.id, item.type, status=outcome.status, expected=expected)
    record = ItemRecord(case=case, author=item.author, error=outcome.error)
    if outcome.status != "ok":
        return record

    result: ChatResult = outcome.value
    case.reason = result.reason
    case.cited = [(index.dataset_ids[s.document_id], s.page) for s in result.sources if s.cited]
    record.answer = result.answer
    record.rewritten_question = result.rewritten_question
    try:
        _judge_faithfulness(result, record, judge, sleep)
        if item.type == "follow_up":
            _judge_rewrite(item, result, record, index, judge, sleep)
    except StopRun as exc:
        record.note = f"judging stopped: {exc}"
        raise _StopAfter(record, str(exc)) from exc
    return record


class _StopAfter(Exception):
    """StopRun raised after an item's answer was recorded, so the record isn't lost."""

    def __init__(self, record: ItemRecord, reason: str):
        super().__init__(reason)
        self.record = record
        self.reason = reason


def _judge_faithfulness(
    result: ChatResult, record: ItemRecord, judge: LLMClient, sleep: Callable[[float], None]
) -> None:
    """Judge an answered question against the passages it cites (uncited answers aren't judged)."""
    cited_numbers = {s.n for s in result.sources if s.cited}
    if not result.found or not cited_numbers:
        return
    cited = [p for p in result.passages if p.n in cited_numbers]
    prompt = build_faithfulness_prompt(result.answer, cited)
    outcome = run_case(
        lambda: generate_json(
            judge, prompt, system=FAITHFULNESS_SYSTEM_PROMPT, schema=FaithfulnessVerdict
        ),
        sleep=sleep,
    )
    if outcome.status != "ok":
        record.judge_error = outcome.error
        return
    claims = outcome.value.claims
    record.case.claims_total = len(claims)
    record.case.claims_supported = sum(c.supported for c in claims)


def _judge_rewrite(
    item: EvalItem,
    result: ChatResult,
    record: ItemRecord,
    index: EvalIndex,
    judge: LLMClient,
    sleep: Callable[[float], None],
) -> None:
    record.case.rewrite_fell_back = result.rewritten_question is None
    if result.rewritten_question is None:
        return
    # Retrieval with the rewrite the model actually wrote (no LLM call).
    pages = usable_pages(rank(result.rewritten_question, index))
    record.rewrite_hit_at_5 = hit_at_k(pages, record.case.expected, 5)
    prompt = build_rewrite_judge_prompt(result.rewritten_question, item.expected_standalone)
    outcome = run_case(
        lambda: generate_json(
            judge, prompt, system=REWRITE_JUDGE_SYSTEM_PROMPT, schema=RewriteVerdict
        ),
        sleep=sleep,
    )
    if outcome.status != "ok":
        record.judge_error = outcome.error
        return
    record.case.rewrite_same_meaning = outcome.value.same_meaning


def retrieval_only_item(item: EvalItem, index: EvalIndex) -> ItemRecord:
    """--no-llm: only what the retrieval layer decides (follow-ups as typed: no rewrite)."""
    kept = retrieve(item.question, list(index.app_ids.values()), index.store).kept
    case = AnswerCase(item.id, item.type, expected=expected_pages(item))
    record = ItemRecord(case=case, author=item.author)
    if kept:
        case.status = "skipped"
        record.note = "needs the LLM"
    else:
        case.reason = "no_relevant_chunks"
    return record


def evaluate(
    dataset: EvalDataset,
    index: EvalIndex,
    *,
    mode: str,
    answerer: CachedLLM | None,
    judge: CachedLLM | None,
    limit: int | None = None,
    judge_model: str | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> RunSummary:
    items = round_robin(dataset.items)[:limit]
    summary = RunSummary(mode=mode, judge_model=judge_model)
    for item in items:
        if summary.stopped:
            case = AnswerCase(item.id, item.type, status="skipped", expected=expected_pages(item))
            summary.records.append(ItemRecord(case, item.author, note=summary.stopped))
            continue
        if answerer is None:
            summary.records.append(retrieval_only_item(item, index))
            continue
        try:
            summary.records.append(answer_item(item, index, answerer, judge, sleep))
        except _StopAfter as stop:
            summary.records.append(stop.record)
            summary.stopped = stop.reason
        except StopRun as exc:
            summary.stopped = str(exc)
            case = AnswerCase(item.id, item.type, status="skipped", expected=expected_pages(item))
            summary.records.append(ItemRecord(case, item.author, note=summary.stopped))
    if answerer is not None:
        clients = {id(answerer): answerer, id(judge): judge}.values()
        summary.real_calls = sum(c.real_calls for c in clients)
        summary.cache_hits = sum(c.cache_hits for c in clients)
    return summary


# --- Report ---


def _refusal_table(cases: Sequence[AnswerCase]) -> list[str]:
    rows = []
    done = [c for c in cases if c.status == "ok"]
    for question_type in TYPE_ORDER:
        of_type = [c for c in done if c.type == question_type]
        if not of_type:
            continue
        rows.append(
            [
                question_type,
                len(of_type),
                pct(rate(c.refused for c in of_type)),
                pct(rate(c.reason == "no_relevant_chunks" for c in of_type)),
                pct(rate(c.reason == "model_declined" for c in of_type)),
                pct(rate(not c.refused for c in of_type)),
            ]
        )
    headers = ["Type", "n", "refused", "by retrieval", "by the model", "answered"]
    return table(headers, rows)


def _retrieval_layer_table(cases: Sequence[AnswerCase]) -> list[str]:
    """--no-llm: refusals by the retrieval layer out of ALL items of each type.

    The other items would need the LLM to decide, so they count as "passed on",
    not as skipped: dropping them would make the refusal rate look perfect.
    Follow-ups are searched as typed, since rewriting needs the LLM.
    """
    lines = ["## Retrieval-layer refusals", ""]
    rows = []
    for question_type in TYPE_ORDER:
        of_type = [c for c in cases if c.type == question_type]
        if of_type:
            refused = rate(c.reason == "no_relevant_chunks" for c in of_type)
            rows.append([question_type, len(of_type), pct(refused)])
    lines += table(["Type", "n", "refused by retrieval (the rest would reach the LLM)"], rows)
    return lines


def _subset_rows(label: str, cases: Sequence[AnswerCase]) -> list[object]:
    refusals = refusal_metrics(cases)
    citations = citation_metrics(cases)
    faithfulness = faithfulness_metrics(cases)
    correct = refusals.correct_refusals
    empty = Rate(0, 0)
    return [
        label,
        len([c for c in cases if c.status == "ok"]),
        pct(correct.get("unanswerable_off_topic", empty)),
        pct(correct.get("unanswerable_on_topic", empty)),
        pct(refusals.false_refusals),
        pct(citations.any_correct),
        pct(faithfulness.claims),
    ]


def render(summary: RunSummary, dataset: EvalDataset) -> str:
    cases = [r.case for r in summary.records]
    lines = run_header("Answer evaluation")
    llm_line = {
        "real": "Answers by the Gemini model configured in the settings.",
        "fake": "**Fake LLM run**: scripted replies, the numbers only show the plumbing works.",
        "none": "**No-LLM run**: only the retrieval layer's refusals are measured.",
    }[summary.mode]
    lines += [
        f"{llm_line} Items evaluated: {len(summary.records)} of {len(dataset.items)} "
        f"(round-robin over question types). Real LLM calls: {summary.real_calls}, "
        f"cache hits: {summary.cache_hits}.",
        "",
    ]
    if summary.mode == "none":
        return "\n".join(lines + _retrieval_layer_table(cases))
    if summary.stopped:
        lines += [f"**The run stopped early:** {summary.stopped}. Rerun to continue (cached "
                  "replies are free).", ""]
    lines += [
        "**Read with care.** Settings were tuned on these same questions, so these numbers are "
        "optimistic; the held-out row (questions written by the project owner) is the unbiased "
        "check. Every percentage shows its counts.",
        "",
        "## Status",
        "",
        "Items with an error (the LLM kept failing, e.g. 503) or skipped (budget or quota used "
        "up) are left out of every metric; they are not counted as wrong.",
        "",
    ]
    lines += table(["Status", "items"], list(status_counts(cases).items()))
    not_ok = [r for r in summary.records if r.case.status != "ok"]
    if not_ok:
        lines += table(
            ["Item", "status", "detail"],
            [[r.case.item_id, r.case.status, r.error or r.note or ""] for r in not_ok],
        )

    lines += [
        "## Refusals",
        "",
        "Which layer refused: retrieval (nothing similar enough, `no_relevant_chunks`) or the "
        "model (it said the answer isn't in the documents, `model_declined`). For answerable "
        "questions and follow-ups, every refusal is a false refusal.",
        "",
    ]
    lines += _refusal_table(cases)

    citations = citation_metrics(cases)
    lines += ["## Citations", "", "Answered questions that have expected pages.", ""]
    lines += table(
        ["answers", "cited sources on an expected page", "≥1 correct citation", "no citation"],
        [[citations.answers, pct(citations.precision), pct(citations.any_correct),
          pct(citations.uncited)]],
    )

    faithfulness = faithfulness_metrics(cases)
    judge_errors = sum(r.judge_error is not None for r in summary.records)
    judge_text = (
        f"a different Gemini model (`{summary.judge_model}`)"
        if summary.judge_model
        else "the same Gemini model that wrote the answers"
    )
    lines += [
        "## Faithfulness (LLM judge)",
        "",
        f"The judge is {judge_text}: the same model family as the answerer, which tends to "
        "agree with its own kind, so these scores are **biased upwards**. Each answer is split "
        "into claims and checked against the full text of the passages it cites; uncited "
        f"answers aren't judged. Judge failures: {judge_errors}.",
        "",
    ]
    lines += table(
        ["judged answers", "supported claims", "fully supported answers"],
        [[faithfulness.judged, pct(faithfulness.claims), pct(faithfulness.fully_supported)]],
    )

    rewrites = rewrite_metrics(cases)
    hits = [r.rewrite_hit_at_5 for r in summary.records if r.rewrite_hit_at_5 is not None]
    lines += ["## Follow-up rewrites", ""]
    lines += table(
        ["follow-ups", "fell back to the original", "same meaning as expected (judge)",
         "hit@5 with the actual rewrite"],
        [[rewrites.follow_ups, pct(rewrites.fell_back), pct(rewrites.same_meaning),
          pct(rate(hits))]],
    )

    held_out = [r.case for r in summary.records if r.author == "user"]
    lines += ["## All questions vs held-out", ""]
    lines += table(
        ["Questions", "n", "off-topic refused", "on-topic unanswerable refused",
         "false refusals", "≥1 correct citation", "supported claims"],
        [
            _subset_rows("all (tuning set)", cases),
            _subset_rows("held-out (owner-written)", held_out),
        ],
    )
    return "\n".join(lines)


def to_json(summary: RunSummary) -> str:
    def default(value):
        if isinstance(value, set):
            return sorted(value)
        raise TypeError(f"can't serialise {type(value).__name__}")

    return json.dumps(asdict(summary), default=default, indent=1, ensure_ascii=False)


def main(argv: list[str] | None = None, *, sleep: Callable[[float], None] = time.sleep) -> int:
    parser = argparse.ArgumentParser(description="Answer evaluation (uses the LLM).")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--documents", type=Path, default=DEFAULT_DOCUMENTS_DIR)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--limit", type=int, default=None, help="evaluate only the first N items")
    parser.add_argument("--max-calls", type=int, default=100, help="real LLM calls, judge included")
    parser.add_argument("--min-interval", type=float, default=1.0, help="seconds between calls")
    parser.add_argument("--judge-model", default=None, help="another Gemini model for the judge")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--fake-llm", action="store_true", help="scripted fake LLM, no API key")
    modes.add_argument("--no-llm", action="store_true", help="retrieval-layer refusals only")
    args = parser.parse_args(argv)

    out = ensure_outside_data(args.out)
    cache = ensure_outside_data(args.cache)
    mode = "fake" if args.fake_llm else "none" if args.no_llm else "real"
    dataset = load_dataset(args.dataset)
    answerer, judge = make_llms(
        mode,
        judge_model=args.judge_model,
        cache_path=cache,
        max_calls=args.max_calls,
        min_interval=args.min_interval,
    )
    with temporary_index(dataset, args.documents) as index:
        summary = evaluate(
            dataset,
            index,
            mode=mode,
            answerer=answerer,
            judge=judge,
            limit=args.limit,
            judge_model=args.judge_model,
            sleep=sleep,
        )

    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    (out / f"answers-{mode}-{stamp}.json").write_text(to_json(summary), encoding="utf-8")
    report = out / f"answer-report{'' if mode == 'real' else '-' + mode}.md"
    report.write_text(render(summary, dataset), encoding="utf-8")
    print(f"Report: {report}")
    if summary.stopped:
        print(f"Stopped early: {summary.stopped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
