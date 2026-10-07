import pytest

from app.llm.base import MAX_RETRY_DELAY, retry_call, retry_stream
from app.llm.errors import ProviderError, RateLimitError


class Flaky:
    """Raises the given errors in order, then returns "ok"."""

    def __init__(self, *errors):
        self.errors = list(errors)
        self.calls = 0

    def __call__(self):
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return "ok"


def run(fn, max_retries=3, base_delay=1.0):
    delays = []
    result = retry_call(fn, max_retries=max_retries, base_delay=base_delay, sleep=delays.append)
    return result, delays


def test_succeeds_after_transient_failures():
    fn = Flaky(RateLimitError(), ProviderError(retryable=True))
    result, delays = run(fn)
    assert result == "ok"
    assert fn.calls == 3
    assert len(delays) == 2


def test_gives_up_after_max_retries():
    fn = Flaky(*[RateLimitError("busy") for _ in range(10)])
    delays = []
    with pytest.raises(RateLimitError):
        retry_call(fn, max_retries=3, base_delay=1.0, sleep=delays.append)
    assert fn.calls == 4  # first try + 3 retries
    assert len(delays) == 3


def test_non_retryable_error_is_raised_immediately():
    fn = Flaky(ProviderError("bad request", status_code=400))
    delays = []
    with pytest.raises(ProviderError):
        retry_call(fn, max_retries=3, base_delay=1.0, sleep=delays.append)
    assert fn.calls == 1
    assert delays == []


def test_daily_quota_is_not_retried():
    fn = Flaky(RateLimitError(daily_quota=True))
    with pytest.raises(RateLimitError):
        run(fn)
    assert fn.calls == 1


def test_delays_grow_exponentially():
    fn = Flaky(*[ProviderError(retryable=True) for _ in range(3)])
    _, delays = run(fn, base_delay=1.0)
    assert 1.0 <= delays[0] <= 1.1
    assert 2.0 <= delays[1] <= 2.2
    assert 4.0 <= delays[2] <= 4.4


def test_waits_at_least_retry_after_but_never_too_long():
    fn = Flaky(RateLimitError(retry_after=5.0), RateLimitError(retry_after=999))
    _, delays = run(fn, base_delay=1.0)
    assert delays[0] >= 5.0
    assert delays[1] == MAX_RETRY_DELAY


def test_other_exceptions_are_not_retried():
    fn = Flaky(ValueError("a bug"))
    with pytest.raises(ValueError):
        run(fn)
    assert fn.calls == 1


def test_stream_retries_until_first_piece():
    attempts = []

    def open_stream():
        attempts.append(1)
        if len(attempts) < 3:
            raise RateLimitError()
        yield "Hello"
        yield " world"

    pieces = list(retry_stream(open_stream, max_retries=3, base_delay=0, sleep=lambda _: None))
    assert pieces == ["Hello", " world"]
    assert len(attempts) == 3


def test_stream_does_not_retry_after_text_was_sent():
    attempts = []

    def open_stream():
        attempts.append(1)
        yield "Hello"
        raise ProviderError("dropped", retryable=True)

    received = []
    with pytest.raises(ProviderError):
        for piece in retry_stream(open_stream, max_retries=3, base_delay=0, sleep=lambda _: None):
            received.append(piece)
    assert received == ["Hello"]
    assert len(attempts) == 1


def test_empty_stream_yields_nothing():
    assert list(retry_stream(lambda: iter([]), max_retries=3, base_delay=0)) == []
