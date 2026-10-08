"""Shared plumbing for the evaluation runners.

- A temporary index (SQLite + Chroma) built with the app's own ingest_pdf, never in backend/data.
- CachedLLM: wraps any LLMClient with a reply cache, a cap on real calls and a pause between them.
- run_case: retries an item after transient LLM errors (429, 503) and records failures
  as "error" instead of letting them count as wrong answers.
"""

import hashlib
import json
import logging
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Generic, TypeVar

from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.db.database import Base, make_engine
from app.llm.base import LLMClient
from app.llm.errors import LLMError, MissingAPIKeyError, RateLimitError
from app.rag.vectorstore import VectorStore
from app.services.ingest import ingest_pdf
from evaluation.dataset import EVAL_DIR, EvalDataset, document_path

logger = logging.getLogger(__name__)

T = TypeVar("T")

BACKEND_DATA_DIR = EVAL_DIR.parent / "data"
DEFAULT_CACHE = EVAL_DIR / ".cache" / "llm_cache.json"  # git-ignored
# Waits before retrying an item after a transient error; GeminiClient has already
# retried quickly inside each call, so these are deliberately long ("retry later").
RETRY_DELAYS = (30.0, 60.0)


# --- Never touch the real data ---


class UnsafePathError(Exception):
    """The evaluation was about to write inside the app's real data folder."""


def ensure_outside_data(path: Path) -> Path:
    """Return `path` resolved, or raise if it is (inside) backend/data or settings.data_dir."""
    resolved = path.resolve()
    for data_dir in {BACKEND_DATA_DIR.resolve(), settings.data_dir.resolve()}:
        if resolved == data_dir or data_dir in resolved.parents:
            raise UnsafePathError(f"refusing to use {resolved}: it is inside {data_dir}")
    return resolved


# --- Temporary index ---


@dataclass
class EvalIndex:
    session: Session
    store: VectorStore
    # dataset document id ("skylab") <-> app document id (random hex from ingest_pdf)
    app_ids: dict[str, str]
    dataset_ids: dict[str, str]


def build_index(
    dataset: EvalDataset,
    documents_dir: Path,
    workdir: Path,
    *,
    max_chars: int = 1800,
    overlap_chars: int = 250,
) -> EvalIndex:
    """Index every dataset document into a new SQLite file and Chroma store under `workdir`."""
    workdir = ensure_outside_data(workdir)  # checked before anything is created
    workdir.mkdir(parents=True, exist_ok=True)  # SQLite won't create the folder itself
    engine = make_engine(f"sqlite:///{workdir / 'eval.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    store = VectorStore(path=workdir / "chroma")
    app_ids = {}
    for doc in dataset.documents:
        path = document_path(doc, documents_dir)  # raises if missing or a different file
        record = ingest_pdf(
            path, doc.file, session, store, max_chars=max_chars, overlap_chars=overlap_chars
        )
        app_ids[doc.id] = record.id
    dataset_ids = {app_id: doc_id for doc_id, app_id in app_ids.items()}
    return EvalIndex(session=session, store=store, app_ids=app_ids, dataset_ids=dataset_ids)


@contextmanager
def temporary_index(
    dataset: EvalDataset, documents_dir: Path, **chunking: int
) -> Iterator[EvalIndex]:
    """build_index in a temporary folder that is deleted afterwards."""
    # Chroma can keep its files open on Windows; a leftover temp folder is harmless.
    with TemporaryDirectory(prefix="studymate-eval-", ignore_cleanup_errors=True) as tmp:
        index = build_index(dataset, documents_dir, Path(tmp), **chunking)
        try:
            yield index
        finally:
            index.session.close()


# --- LLM: cache, call cap, pause ---


class BudgetExhausted(Exception):
    """--max-calls real LLM calls have been made. Deliberately not an LLMError, so the
    chat pipeline (which tolerates LLM errors in rewriting) can't swallow it."""


@dataclass
class RunState:
    """What every LLM client of one run shares: the call budget, the time of the last
    real call (for the pause) and the reply cache. The answerer and the judge may be
    different models, but they spend the same quota and must not overwrite each
    other's cache entries."""

    max_calls: int
    cache_path: Path | None = None
    calls: int = 0
    last_call_end: float | None = None
    cache: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, max_calls: int, cache_path: Path | None = None) -> "RunState":
        state = cls(max_calls=max_calls, cache_path=cache_path)
        if cache_path is not None and cache_path.exists():
            state.cache = json.loads(cache_path.read_text(encoding="utf-8"))
        return state

    def save(self) -> None:
        if self.cache_path is None:
            return
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        # Write a temp file, then swap it in, so an interrupted run never leaves half a cache.
        tmp = self.cache_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.cache, ensure_ascii=False, indent=0), encoding="utf-8")
        tmp.replace(self.cache_path)


class CachedLLM(LLMClient):
    """Wraps an LLMClient for evaluation runs.

    - Replies are cached on disk by (model, system prompt, prompt), so a rerun, or a
      run that stopped halfway, only pays for prompts it hasn't seen.
    - At most `state.max_calls` real calls per run (cache hits are free). Failed calls
      count too: they still use quota.
    - At least `min_interval` seconds between the start of one real call and the end of
      the previous one, to stay friendly with free-tier rate limits.
    `sleep` and `clock` are injectable so tests don't wait.
    """

    def __init__(
        self,
        inner: LLMClient,
        *,
        model: str,
        state: RunState,
        min_interval: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.inner = inner
        self.model = model
        self.state = state
        self.min_interval = min_interval
        self._sleep = sleep
        self._clock = clock
        self.real_calls = 0  # this client's own real calls (the budget counts all clients)
        self.cache_hits = 0

    def _key(self, prompt: str, system: str | None) -> str:
        raw = json.dumps([self.model, system, prompt], ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def generate(self, prompt: str, system: str | None = None) -> str:
        key = self._key(prompt, system)
        if key in self.state.cache:
            self.cache_hits += 1
            return self.state.cache[key]
        if self.state.calls >= self.state.max_calls:
            raise BudgetExhausted(f"--max-calls {self.state.max_calls} reached")
        self._pause()
        self.state.calls += 1
        self.real_calls += 1
        try:
            reply = self.inner.generate(prompt, system=system)
        finally:
            self.state.last_call_end = self._clock()
        self.state.cache[key] = reply
        self.state.save()
        return reply

    def stream(self, prompt: str, system: str | None = None) -> Iterator[str]:
        # The evaluation never streams; one piece keeps the interface complete.
        yield self.generate(prompt, system=system)

    def _pause(self) -> None:
        if self.state.last_call_end is None:
            return
        wait = self.min_interval - (self._clock() - self.state.last_call_end)
        if wait > 0:
            self._sleep(wait)


# --- Running one item ---


class StopRun(Exception):
    """Nothing more can be evaluated in this run (quota, budget or setup problem)."""


@dataclass
class Outcome(Generic[T]):
    status: str  # "ok" or "error"
    value: T | None = None
    error: str | None = None  # error class name, never its message (it may contain text)
    attempts: int = 1
    notes: list[str] = field(default_factory=list)


def run_case(
    fn: Callable[[], T],
    *,
    retry_delays: tuple[float, ...] = RETRY_DELAYS,
    sleep: Callable[[float], None] = time.sleep,
) -> Outcome[T]:
    """Run one evaluation item, waiting and retrying after transient LLM errors.

    - Transient (429 that isn't the daily quota, 503 and other 5xx, timeouts): wait and
      try again; if it still fails, the item is "error", which metrics leave out.
    - Other LLM errors (e.g. the judge's JSON was unusable twice): "error" right away.
    - Daily quota, missing API key or the call cap: StopRun, since every later item
      would fail the same way.
    """
    attempts = 0
    while True:
        attempts += 1
        try:
            return Outcome("ok", value=fn(), attempts=attempts)
        except BudgetExhausted as exc:
            raise StopRun(str(exc)) from exc
        except (MissingAPIKeyError, RateLimitError) as exc:
            if isinstance(exc, MissingAPIKeyError) or exc.daily_quota:
                raise StopRun(type(exc).__name__) from exc
            error = exc
        except LLMError as exc:
            error = exc
        if not error.retryable or attempts > len(retry_delays):
            logger.warning("eval item failed error=%s attempts=%d", type(error).__name__, attempts)
            return Outcome("error", error=type(error).__name__, attempts=attempts)
        sleep(retry_delays[attempts - 1])


# --- Choosing the LLM ---

LLM_MODES = ("real", "fake", "none")


def make_llms(
    mode: str,
    *,
    judge_model: str | None = None,
    cache_path: Path | None = DEFAULT_CACHE,
    max_calls: int = 100,
    min_interval: float = 1.0,
) -> tuple[CachedLLM | None, CachedLLM | None]:
    """The (answerer, judge) of a run: (None, None) for --no-llm, the scripted fake,
    or Gemini behind the cache. Both share one RunState (budget, pause, cache).

    Only "real" creates a GeminiClient (which needs the API key from the settings);
    the judge is the answering model unless `judge_model` names another one. The fake
    never caches, so fake replies can't end up in the real cache.
    """
    if mode == "none":
        return None, None
    if mode == "fake":
        from evaluation.fake_llm import ScriptedEvalLLM

        fake = CachedLLM(
            ScriptedEvalLLM(), model="fake", state=RunState.load(max_calls), min_interval=0
        )
        return fake, fake
    if mode == "real":
        from app.llm.gemini import GeminiClient

        state = RunState.load(max_calls, cache_path)
        client = GeminiClient()
        answerer = CachedLLM(client, model=client.model, state=state, min_interval=min_interval)
        if not judge_model or judge_model == client.model:
            return answerer, answerer
        judge_client = GeminiClient(model=judge_model)
        judge = CachedLLM(judge_client, model=judge_model, state=state, min_interval=min_interval)
        return answerer, judge
    raise ValueError(f"unknown LLM mode {mode!r}; expected one of {LLM_MODES}")
