import random
import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable, Iterator
from typing import TypeVar

from app.llm.errors import LLMError

T = TypeVar("T")

# Never wait longer than this between two attempts.
MAX_RETRY_DELAY = 30.0


class LLMClient(ABC):
    """What the rest of the app needs from a language model, whatever the provider."""

    @abstractmethod
    def generate(self, prompt: str, system: str | None = None) -> str:
        """Return the full answer to `prompt`. `system` holds optional instructions."""

    @abstractmethod
    def stream(self, prompt: str, system: str | None = None) -> Iterator[str]:
        """Yield the answer piece by piece as the model produces it."""


def retry_call(
    fn: Callable[[], T],
    *,
    max_retries: int,
    base_delay: float,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Call `fn`, retrying LLM errors marked `retryable` with exponential backoff.

    Waits base_delay, 2x, 4x, ... (plus a little random jitter so many clients
    don't retry in lockstep). If the provider told us how long to wait, wait at least that.
    """
    attempt = 0
    while True:
        try:
            return fn()
        except LLMError as e:
            if not e.retryable or attempt >= max_retries:
                raise
            delay = base_delay * 2**attempt
            delay = max(delay, getattr(e, "retry_after", None) or 0)
            delay = min(delay * (1 + random.random() * 0.1), MAX_RETRY_DELAY)
            sleep(delay)
            attempt += 1


def retry_stream(
    open_stream: Callable[[], Iterable[str]],
    *,
    max_retries: int,
    base_delay: float,
    sleep: Callable[[float], None] = time.sleep,
) -> Iterator[str]:
    """Stream with retries, but only until the first piece arrives.

    Once text has been sent to the caller, retrying would repeat it, so any
    later error is raised as it is.
    """

    def first_piece():
        pieces = iter(open_stream())
        return next(pieces, None), pieces

    head, rest = retry_call(first_piece, max_retries=max_retries, base_delay=base_delay, sleep=sleep)
    if head is None:
        return
    yield head
    yield from rest
