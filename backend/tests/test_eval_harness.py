from pathlib import Path

import pytest

import app.llm.gemini
from app.config import settings
from app.llm.errors import (
    InvalidLLMOutputError,
    MissingAPIKeyError,
    ProviderError,
    RateLimitError,
)
from app.rag.prompts import (
    REWRITE_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    HistoryMessage,
    build_rewrite_prompt,
)
from evaluation.fake_llm import FAKE_ANSWER, ScriptedEvalLLM
from evaluation.harness import (
    BACKEND_DATA_DIR,
    BudgetExhausted,
    CachedLLM,
    RunState,
    StopRun,
    UnsafePathError,
    build_index,
    ensure_outside_data,
    make_llms,
    run_case,
    temporary_index,
)
from evaluation.metrics import AnswerCase, refusal_metrics
from tests.fakes import FakeLLMClient
from tests.test_eval_dataset import answerable, make_dataset

EVAL_SOURCES = Path(__file__).parent.parent / "evaluation"


class FakeClock:
    """A clock that only moves when `sleep` is called (or the test moves it)."""

    def __init__(self):
        self.now = 100.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def cached(inner, tmp_path=None, clock=None, max_calls=100, model="m", state=None, **kwargs):
    """A CachedLLM with a fake clock; with `tmp_path`, its cache lives in a file there."""
    clock = clock or FakeClock()
    state = state or RunState.load(max_calls, tmp_path and tmp_path / "cache.json")
    return CachedLLM(inner, model=model, state=state, sleep=clock.sleep, clock=clock, **kwargs)


# --- ~1 second pause between real calls ---


def test_real_calls_are_at_least_one_second_apart():
    clock = FakeClock()
    llm = cached(FakeLLMClient(), clock=clock, min_interval=1.0)

    llm.generate("p1")  # first call: nothing to wait for
    llm.generate("p2")  # straight after: waits the full second
    clock.now += 0.4
    llm.generate("p3")  # 0.4 s already passed: waits the rest
    clock.now += 5
    llm.generate("p4")  # long enough ago: no wait

    assert clock.sleeps == [1.0, pytest.approx(0.6)]


def test_cache_hits_never_wait(tmp_path):
    clock = FakeClock()
    llm = cached(FakeLLMClient(), tmp_path, clock=clock)
    llm.generate("p1")

    for _ in range(3):
        llm.generate("p1")

    assert clock.sleeps == []
    assert (llm.real_calls, llm.cache_hits) == (1, 3)


# --- --max-calls cap ---


def test_max_calls_caps_real_calls_but_not_cache_hits(tmp_path):
    inner = FakeLLMClient()
    llm = cached(inner, tmp_path, max_calls=2)
    llm.generate("p1")
    llm.generate("p2")

    with pytest.raises(BudgetExhausted):
        llm.generate("p3")
    assert llm.generate("p1") == "Fake answer."  # cached: still allowed
    assert len(inner.calls) == 2


def test_failed_calls_count_towards_the_cap_and_are_not_cached(tmp_path):
    inner = FakeLLMClient(replies=[ProviderError("503", status_code=503, retryable=True), "ok"])
    llm = cached(inner, tmp_path, max_calls=2)

    with pytest.raises(ProviderError):
        llm.generate("p1")
    assert llm.generate("p1") == "ok"  # the failure wasn't cached, so this is a real call
    with pytest.raises(BudgetExhausted):
        llm.generate("p2")


def test_reaching_the_cap_stops_the_run():
    llm = cached(FakeLLMClient(), max_calls=0)

    with pytest.raises(StopRun, match="max-calls"):
        run_case(lambda: llm.generate("p1"), sleep=lambda s: None)


# --- cache ---


def test_second_run_with_the_same_cache_makes_no_real_calls(tmp_path):
    first = cached(FakeLLMClient(reply="A"), tmp_path)
    first.generate("p1", system="s")

    inner = FakeLLMClient(reply="B")
    second = cached(inner, tmp_path)

    assert second.generate("p1", system="s") == "A"
    assert inner.calls == [] and second.real_calls == 0
    assert cached(inner, tmp_path, model="other").generate("p1", system="s") == "B"


def test_answerer_and_judge_share_one_budget_pause_and_cache(tmp_path):
    clock = FakeClock()
    state = RunState.load(max_calls=2, cache_path=tmp_path / "cache.json")
    answerer = cached(FakeLLMClient(reply="answer"), clock=clock, state=state, model="m1")
    judge = cached(FakeLLMClient(reply="verdict"), clock=clock, state=state, model="m2")

    answerer.generate("p1")
    judge.generate("p2")  # the judge waits after the answerer's call too

    assert clock.sleeps == [1.0]
    with pytest.raises(BudgetExhausted):
        answerer.generate("p3")  # 2 calls in total: the budget is used up
    # Both replies survived in the one cache file (neither client overwrote the other).
    reloaded = RunState.load(max_calls=0, cache_path=tmp_path / "cache.json")
    assert sorted(reloaded.cache.values()) == ["answer", "verdict"]


# --- 429 then success, 503 that never recovers ---


def test_429_then_success_is_a_normal_result():
    sleeps = []
    llm = cached(FakeLLMClient(replies=[RateLimitError("429", retry_after=5), "Answer."]))

    outcome = run_case(lambda: llm.generate("p1"), sleep=sleeps.append)

    assert (outcome.status, outcome.value, outcome.attempts) == ("ok", "Answer.", 2)
    assert sleeps == [30.0]  # waited before retrying the item


def test_503_that_never_recovers_is_an_error_not_a_wrong_answer():
    sleeps = []
    unavailable = ProviderError("503 UNAVAILABLE", status_code=503, retryable=True)
    always_503 = FakeLLMClient(error=unavailable)
    llm = cached(always_503)

    outcome = run_case(lambda: llm.generate("p1"), sleep=sleeps.append)

    assert (outcome.status, outcome.error, outcome.attempts) == ("error", "ProviderError", 3)
    assert sleeps == [30.0, 60.0]
    # Recorded as an error, it is left out of the metrics instead of counting as a refusal.
    cases = [
        AnswerCase("a1", "answerable", reason="ok"),
        AnswerCase("a2", "answerable", status=outcome.status),
    ]
    assert refusal_metrics(cases).false_refusals.total == 1


def test_non_transient_errors_are_recorded_without_waiting():
    sleeps = []

    def judge():
        raise InvalidLLMOutputError("bad JSON twice")

    outcome = run_case(judge, sleep=sleeps.append)

    assert (outcome.status, outcome.error) == ("error", "InvalidLLMOutputError")
    assert outcome.attempts == 1
    assert sleeps == []


@pytest.mark.parametrize(
    "error", [RateLimitError("429", daily_quota=True), MissingAPIKeyError("no key")]
)
def test_daily_quota_or_missing_key_stops_the_run(error):
    def fail():
        raise error

    with pytest.raises(StopRun):
        run_case(fail, sleep=lambda s: None)


# --- never inside backend/data ---


@pytest.mark.parametrize(
    "path",
    [
        BACKEND_DATA_DIR,
        BACKEND_DATA_DIR / "eval",
        BACKEND_DATA_DIR / "chroma",
        BACKEND_DATA_DIR.parent / "evaluation" / ".." / "data" / "x",  # resolved before checking
    ],
)
def test_guard_refuses_backend_data(path):
    with pytest.raises(UnsafePathError):
        ensure_outside_data(path)


def test_guard_also_refuses_the_configured_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "real-data")

    with pytest.raises(UnsafePathError):
        ensure_outside_data(tmp_path / "real-data" / "eval")
    assert ensure_outside_data(tmp_path / "elsewhere") == (tmp_path / "elsewhere").resolve()


def test_build_index_refuses_backend_data_before_creating_anything(tmp_path):
    dataset = make_dataset(tmp_path, [answerable()])
    target = BACKEND_DATA_DIR / "eval-guard-test"

    with pytest.raises(UnsafePathError):
        build_index(dataset, tmp_path, target)
    assert not target.exists()


# --- temporary index ---


LONG_PAGES = [
    "Mutation adds variety to the population of a genetic algorithm.",
    "Selection keeps the fittest individuals of the population alive.",
]


def test_temporary_index_uses_the_app_ingest_and_maps_ids(tmp_path):
    # Pages need 50+ characters: shorter fragments are dropped by the chunker.
    dataset = make_dataset(tmp_path, [answerable()], pages=LONG_PAGES)

    with temporary_index(dataset, tmp_path) as index:
        app_id = index.app_ids["ga"]
        assert index.dataset_ids == {app_id: "ga"}
        results = index.store.search("What does mutation add?", k=1, document_ids=[app_id])
        assert (results[0].document_id, results[0].page) == (app_id, 1)
        workdir = Path(index.store._client.get_settings().persist_directory)
        assert BACKEND_DATA_DIR.resolve() not in workdir.resolve().parents


def test_chunk_size_reaches_ingest(tmp_path):
    page = "\n".join(f"Sentence {i} talks about mutation in genetic algorithms." for i in range(30))
    dataset = make_dataset(tmp_path, [answerable(evidence=["Sentence 1 talks"])], pages=[page])

    small = build_index(dataset, tmp_path, tmp_path / "small", max_chars=200, overlap_chars=0)
    large = build_index(dataset, tmp_path, tmp_path / "large")

    small_count = len(small.store.get_chunks(small.app_ids["ga"]))
    large_count = len(large.store.get_chunks(large.app_ids["ga"]))
    assert small_count > large_count


# --- choosing the LLM, and .env ---


def test_no_llm_and_fake_modes_never_create_a_gemini_client(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("GeminiClient must not be created in this mode")

    monkeypatch.setattr(app.llm.gemini, "GeminiClient", refuse)

    assert make_llms("none") == (None, None)
    answerer, judge = make_llms("fake")
    assert isinstance(answerer.inner, ScriptedEvalLLM) and judge is answerer
    assert answerer.state.cache_path is None  # fake replies never reach the real cache


def test_real_mode_gets_the_key_only_from_settings(monkeypatch):
    # The evaluation has no key handling of its own: without a key in the settings it fails.
    monkeypatch.setattr(settings, "gemini_api_key", "")

    with pytest.raises(MissingAPIKeyError):
        make_llms("real")


def test_evaluation_code_never_reads_env_files():
    for source in EVAL_SOURCES.rglob("*.py"):
        text = source.read_text(encoding="utf-8")
        for forbidden in (".env", "dotenv", "env_file", "os.environ", "getenv"):
            assert forbidden not in text, f"{source.name} mentions {forbidden}"


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError):
        make_llms("gpt")


# --- the scripted fake ---


def test_fake_llm_answers_and_rewrites():
    llm = ScriptedEvalLLM()
    history = [HistoryMessage("user", "What is the twin pole sail?")]

    prompt = build_rewrite_prompt("Who put it up?", history)

    rewrite = llm.generate(prompt, system=REWRITE_SYSTEM_PROMPT)

    assert rewrite == "Who put it up?"
    assert llm.generate("passages...", system=SYSTEM_PROMPT) == FAKE_ANSWER
    with pytest.raises(ValueError):
        llm.generate("x", system="some new judge prompt")
