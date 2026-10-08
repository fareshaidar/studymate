import json

import pytest

import app.llm.gemini
from app.config import settings
from app.llm.errors import ProviderError
from evaluation.dataset import EvalItem
from evaluation.harness import CachedLLM, RunState, build_index, make_llms
from evaluation.judge_prompts import FAITHFULNESS_SYSTEM_PROMPT
from evaluation.metrics import citation_metrics, refusal_metrics
from evaluation.run_answer_eval import evaluate, main, render, round_robin
from tests.fakes import FakeLLMClient
from tests.test_eval_retrieval import args, tiny_dataset

NO_SLEEP = {"sleep": lambda seconds: None}
VALID_VERDICT = '{"claims": [{"claim": "c", "supported": true}]}'


@pytest.fixture
def setup(tmp_path, monkeypatch):
    """The tiny dataset, its JSON file, and an index where every chunk passes the threshold."""
    monkeypatch.setattr(settings, "min_similarity", 0.0)
    dataset = tiny_dataset(tmp_path)
    (tmp_path / "dataset.json").write_text(dataset.model_dump_json(), encoding="utf-8")
    index = build_index(dataset, tmp_path, tmp_path / "index")
    return dataset, index


def client(inner, state):
    return CachedLLM(inner, model="m", state=state, min_interval=0)


# --- whole runs through main() ---


def test_fake_llm_run_writes_report_and_json(tmp_path, setup, monkeypatch):
    monkeypatch.setattr(settings, "gemini_model", "my-private-model-name")
    out = tmp_path / "results"

    assert main(args(tmp_path, out) + ["--fake-llm"], **NO_SLEEP) == 0

    report = (out / "answer-report-fake.md").read_text(encoding="utf-8")
    for heading in (
        "## Status",
        "## Refusals",
        "## Citations",
        "## Faithfulness",
        "## Follow-up rewrites",
        "## All questions vs held-out",
        "biased upwards",
        "tuned on these same questions",
    ):
        assert heading in report
    assert "| held-out (owner-written) | 1 |" in report
    (json_file,) = out.glob("answers-fake-*.json")
    data = json.loads(json_file.read_text(encoding="utf-8"))
    assert [r["case"]["status"] for r in data["records"]] == ["ok"] * 5
    follow_up = next(r for r in data["records"] if r["case"]["type"] == "follow_up")
    assert follow_up["case"]["rewrite_same_meaning"] is True
    # The model name from the local settings is never printed.
    assert "my-private-model-name" not in report + json_file.read_text(encoding="utf-8")


def test_no_llm_run_creates_no_client_and_only_reports_refusals(tmp_path, setup, monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("no LLM client in --no-llm mode")

    monkeypatch.setattr(app.llm.gemini, "GeminiClient", refuse)
    monkeypatch.setattr(settings, "min_similarity", 0.99)  # retrieval refuses everything
    out = tmp_path / "results"

    assert main(args(tmp_path, out) + ["--no-llm"], **NO_SLEEP) == 0

    report = (out / "answer-report-none.md").read_text(encoding="utf-8")
    assert "## Refusals" in report and "## Citations" not in report
    assert "| unanswerable_off_topic | 1 | 100% (1/1) | 100% (1/1) |" in report


def test_limit_takes_items_round_robin(tmp_path, setup):
    out = tmp_path / "results"

    main(args(tmp_path, out) + ["--fake-llm", "--limit", "3"], **NO_SLEEP)

    (json_file,) = out.glob("answers-fake-*.json")
    records = json.loads(json_file.read_text(encoding="utf-8"))["records"]
    types = [r["case"]["type"] for r in records]
    assert types == ["answerable", "follow_up", "unanswerable_off_topic"]


def test_round_robin_interleaves_types():
    def item(item_id, question_type):
        extra = {"document": "d", "pages": [1], "evidence": ["e"]}
        if question_type == "unanswerable_off_topic":
            extra = {}
        return EvalItem(
            id=item_id, type=question_type, question="q?", reference_answer="r", **extra
        )

    items = [
        item("a1", "answerable"),
        item("a2", "answerable"),
        item("o1", "unanswerable_off_topic"),
    ]

    assert [i.id for i in round_robin(items)] == ["a1", "o1", "a2"]


# --- budget, errors and the judge, through evaluate() ---


def test_reaching_max_calls_keeps_partial_results_and_skips_the_rest(setup):
    dataset, index = setup
    answerer, judge = make_llms("fake", max_calls=1)

    summary = evaluate(dataset, index, mode="fake", answerer=answerer, judge=judge, **NO_SLEEP)

    first, *rest = summary.records
    # The one call answered the first question; its judgement didn't fit in the budget.
    assert (first.case.status, first.case.reason) == ("ok", "ok")
    assert first.case.claims_total is None and "max-calls" in first.note
    assert {r.case.status for r in rest} == {"skipped"}
    assert "max-calls" in summary.stopped
    assert "The run stopped early" in render(summary, dataset)


def test_503_that_never_recovers_is_reported_as_error_not_wrong(setup):
    dataset, index = setup
    unavailable = ProviderError("503 UNAVAILABLE", status_code=503, retryable=True)
    llm = client(FakeLLMClient(error=unavailable), RunState.load(100))
    sleeps = []

    summary = evaluate(
        dataset, index, mode="real", answerer=llm, judge=llm, limit=2, sleep=sleeps.append
    )

    assert [(r.case.status, r.error) for r in summary.records] == [("error", "ProviderError")] * 2
    assert sleeps == [30.0, 60.0] * 2
    cases = [r.case for r in summary.records]
    assert refusal_metrics(cases).false_refusals.total == 0  # not counted as refusals
    assert "| error | 2 |" in render(summary, dataset)


def test_judge_failure_keeps_the_answer_in_the_other_metrics(setup):
    dataset, index = setup
    state = RunState.load(100)
    answerer = client(FakeLLMClient(reply="Mutation adds variety [1]."), state)
    judge = client(FakeLLMClient(reply="Looks fine to me!"), state)  # never valid JSON

    summary = evaluate(
        dataset, index, mode="real", answerer=answerer, judge=judge, limit=1, **NO_SLEEP
    )

    (record,) = summary.records
    assert record.judge_error == "InvalidLLMOutputError"
    assert record.case.claims_total is None
    assert citation_metrics([record.case]).answers == 1  # still counted for citations


def test_judge_sees_only_the_cited_passages(setup):
    dataset, index = setup
    state = RunState.load(100)
    answerer = client(FakeLLMClient(reply="Selection keeps the fittest [2]."), state)
    judge_inner = FakeLLMClient(reply=VALID_VERDICT)

    evaluate(
        dataset,
        index,
        mode="real",
        answerer=answerer,
        judge=client(judge_inner, state),
        limit=1,
        **NO_SLEEP,
    )

    ((prompt, system),) = judge_inner.calls
    assert system == FAITHFULNESS_SYSTEM_PROMPT
    assert "[2] (" in prompt and "[1] (" not in prompt and "[3] (" not in prompt
    assert "Selection keeps the fittest [2]." in prompt
