import logging
import re
import time
from collections.abc import Callable, Iterator

import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from app.config import settings
from app.llm.base import LLMClient, retry_call, retry_stream
from app.llm.errors import LLMError, MissingAPIKeyError, ProviderError, RateLimitError

logger = logging.getLogger(__name__)

EMPTY_ANSWER_MESSAGE ="The AI couldn't produce an answer for this request. Try rephrasing it."


class GeminiClient(LLMClient):
    """LLMClient backed by Google's Gemini API (google-genai SDK).

    Everything defaults to `settings`. `client` lets tests pass a fake SDK object,
    and `sleep` lets them skip the real waiting between retries.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        *,
        client=None,
        max_retries: int | None = None,
        base_delay: float | None = None,
        timeout_seconds: int | None = None,
        fallback_model: str | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        key = settings.gemini_api_key if api_key is None else api_key
        if not key:
            raise MissingAPIKeyError("GEMINI_API_KEY is not set.")
        self.model = model or settings.gemini_model
        fallback = settings.gemini_fallback_model if fallback_model is None else fallback_model
        # Used for the rest of a request once the primary model returns 503. Empty = off.
        self.fallback_model = fallback if fallback and fallback != self.model else None
        timeout = timeout_seconds or settings.llm_timeout_seconds
        self._client = client or genai.Client(
            api_key=key,
            http_options=types.HttpOptions(
                timeout=timeout * 1000,  # the SDK expects milliseconds
                # One attempt per SDK call: retry_call is our only retry layer.
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )
        self._retry = {
            "max_retries": settings.llm_max_retries if max_retries is None else max_retries,
            "base_delay": settings.llm_retry_base_delay if base_delay is None else base_delay,
            "sleep": sleep,
        }

    def generate(self, prompt: str, system: str | None = None) -> str:
        model = self.model  # per request: may switch to the fallback

        def attempt() -> str:
            with _translated_errors(model):
                response = self._client.models.generate_content(
                    model=model, contents=prompt, config=_config(system)
                )
            if not response.text:
                raise ProviderError(
                    f"Gemini returned no text ({_why_empty(response)}).",
                    user_message=EMPTY_ANSWER_MESSAGE,
                )
            return response.text

        def call() -> str:
            nonlocal model
            try:
                return attempt()
            except ProviderError as e:
                if not self._should_fall_back(e, model):
                    raise
                model = self._switch_to_fallback(e)
                return attempt()

        return retry_call(call, **self._retry)

    def stream(self, prompt: str, system: str | None = None) -> Iterator[str]:
        model = self.model  # per request: may switch to the fallback

        def open_stream_for(current: str) -> Iterator[str]:
            last_chunk = None
            got_text = False
            with _translated_errors(current):
                for chunk in self._client.models.generate_content_stream(
                    model=current, contents=prompt, config=_config(system)
                ):
                    last_chunk = chunk
                    if chunk.text:
                        got_text = True
                        yield chunk.text
            if not got_text:
                raise ProviderError(
                    f"Gemini streamed no text ({_why_empty(last_chunk)}).",
                    user_message=EMPTY_ANSWER_MESSAGE,
                )

        def open_stream() -> Iterator[str]:
            nonlocal model
            started = False
            try:
                for piece in open_stream_for(model):
                    started = True
                    yield piece
            except ProviderError as e:
                # Once text was sent, switching models would repeat it.
                if started or not self._should_fall_back(e, model):
                    raise
                model = self._switch_to_fallback(e)
                yield from open_stream_for(model)

        return retry_stream(open_stream, **self._retry)

    def _should_fall_back(self, error: ProviderError, current_model: str) -> bool:
        return (
            error.status_code == 503
            and self.fallback_model is not None
            and current_model != self.fallback_model
        )

    def _switch_to_fallback(self, error: ProviderError) -> str:
        logger.warning(
            "Gemini model %s unavailable (%s); using fallback %s for this request",
            self.model,
            error,
            self.fallback_model,
        )
        return self.fallback_model


def _config(system: str | None) -> types.GenerateContentConfig | None:
    return types.GenerateContentConfig(system_instruction=system) if system else None


class _translated_errors:
    """Context manager that turns SDK / network exceptions into our LLMError types."""

    def __init__(self, model: str):
        self.model = model

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc is None or isinstance(exc, LLMError) or not isinstance(exc, Exception):
            return False
        translated = translate_error(exc, self.model)
        if translated is exc:
            return False
        raise translated from exc


def translate_error(e: Exception, model: str = "") -> Exception:
    """Map a google-genai / httpx exception to one of our errors (unknown ones pass through)."""
    if isinstance(e, genai_errors.APIError):
        code = e.code
        detail = f"Gemini error {code} {e.status}: {e.message}"
        if code == 429:
            return RateLimitError(detail, retry_after=_retry_after(e), daily_quota=_is_daily_quota(e))
        if code in (401, 403) or "API key" in (e.message or ""):
            return ProviderError(
                detail,
                status_code=code,
                user_message="The AI service rejected the API key. Check GEMINI_API_KEY.",
            )
        if code == 404:
            return ProviderError(
                f"{detail} (model: {model})",
                status_code=code,
                user_message="The configured AI model isn't available. Check GEMINI_MODEL.",
            )
        return ProviderError(detail, status_code=code, retryable=code == 408 or code >= 500)
    if isinstance(e, httpx.TimeoutException):
        return ProviderError(
            "Gemini request timed out.",
            retryable=True,
            user_message="The AI service took too long to respond. Please try again.",
        )
    if isinstance(e, httpx.TransportError):
        return ProviderError(
            f"Network error talking to Gemini: {type(e).__name__}",
            retryable=True,
            user_message="Couldn't reach the AI service. Check your internet connection.",
        )
    return e


def _error_details(e: genai_errors.APIError) -> list[dict]:
    """The structured `details` list Google attaches to errors (QuotaFailure, RetryInfo, ...)."""
    body = e.details if isinstance(e.details, dict) else {}
    details = body.get("error", body).get("details", [])
    return [d for d in details if isinstance(d, dict)] if isinstance(details, list) else []


def _is_daily_quota(e: genai_errors.APIError) -> bool:
    for detail in _error_details(e):
        for violation in detail.get("violations", []):
            if "PerDay" in str(violation.get("quotaId", "")):
                return True
    return "per day" in (e.message or "").lower()


def _retry_after(e: genai_errors.APIError) -> float | None:
    """Read RetryInfo's retryDelay (e.g. "34s" or "1.5s") if Google sent one."""
    for detail in _error_details(e):
        match = re.fullmatch(r"(\d+(?:\.\d+)?)s", str(detail.get("retryDelay", "")))
        if match:
            return float(match.group(1))
    return None


def _why_empty(response) -> str:
    """Best-effort reason for an answer with no text, e.g. a safety block."""
    feedback = getattr(response, "prompt_feedback", None)
    if feedback is not None and getattr(feedback, "block_reason", None):
        return f"prompt blocked: {feedback.block_reason}"
    candidates = getattr(response, "candidates", None) or []
    if candidates and getattr(candidates[0], "finish_reason", None):
        return f"finish reason: {candidates[0].finish_reason}"
    return "no reason given"
