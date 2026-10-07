from types import SimpleNamespace

import httpx
import pytest
from google import genai
from google.genai import errors as genai_errors

from app.config import settings
from app.llm.errors import MissingAPIKeyError, ProviderError, RateLimitError
from app.llm.gemini import GeminiClient


def api_error(code, status="", message="", details=None):
    body = {"error": {"code": code, "status": status, "message": message, "details": details or []}}
    cls = genai_errors.ServerError if code >= 500 else genai_errors.ClientError
    return cls(code, body)


def rate_limited(daily=False, retry_delay=None):
    details = []
    if daily:
        details.append({"violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]})
    if retry_delay:
        details.append({"retryDelay": retry_delay})
    return api_error(429, "RESOURCE_EXHAUSTED", "Quota exceeded.", details)


def reply(text):
    return SimpleNamespace(text=text, prompt_feedback=None, candidates=[])


class FakeModels:
    """Mimics `client.models`. Each call takes the next outcome: an exception or a result."""

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def _next(self, kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def generate_content(self, **kwargs):
        return self._next(kwargs)

    def generate_content_stream(self, **kwargs):
        # Like the SDK: a list of chunks, where an exception item fails mid-stream.
        for item in self._next(kwargs):
            if isinstance(item, Exception):
                raise item
            yield reply(item)


def make_client(*outcomes, **kwargs):
    models = FakeModels(outcomes)
    client = GeminiClient(
        api_key="test-key", client=SimpleNamespace(models=models), sleep=lambda _: None, **kwargs
    )
    return client, models


def test_missing_key_raises(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "")
    with pytest.raises(MissingAPIKeyError) as info:
        GeminiClient(client=SimpleNamespace(models=None))
    assert "API key" in info.value.user_message


def test_timeout_and_key_are_passed_to_the_sdk(monkeypatch):
    created = {}
    monkeypatch.setattr(genai, "Client", lambda **kwargs: created.update(kwargs))
    monkeypatch.setattr(settings, "llm_timeout_seconds", 60)
    GeminiClient(api_key="test-key")
    assert created["api_key"] == "test-key"
    assert created["http_options"].timeout == 60_000  # milliseconds


def test_generate_uses_model_from_settings_and_system_prompt(monkeypatch):
    monkeypatch.setattr(settings, "gemini_model", "gemini-test-model")
    client, models = make_client(reply("Hi there"))
    assert client.generate("Hello", system="Be kind.") == "Hi there"
    call = models.calls[0]
    assert call["model"] == "gemini-test-model"
    assert call["contents"] == "Hello"
    assert call["config"].system_instruction == "Be kind."


def test_generate_without_system_sends_no_config():
    client, models = make_client(reply("Hi"))
    client.generate("Hello")
    assert models.calls[0]["config"] is None


def test_rate_limit_then_success():
    client, models = make_client(rate_limited(), reply("Done"))
    assert client.generate("Hello") == "Done"
    assert len(models.calls) == 2


def test_rate_limit_every_time_raises_after_retries():
    client, models = make_client(*[rate_limited() for _ in range(4)], max_retries=3)
    with pytest.raises(RateLimitError) as info:
        client.generate("Hello")
    assert len(models.calls) == 4
    assert not info.value.daily_quota


def test_daily_quota_is_not_retried():
    client, models = make_client(rate_limited(daily=True))
    with pytest.raises(RateLimitError) as info:
        client.generate("Hello")
    assert len(models.calls) == 1
    assert info.value.daily_quota
    assert "tomorrow" in info.value.user_message


def test_retry_delay_from_google_is_respected():
    waits = []
    models = FakeModels([rate_limited(retry_delay="7s"), reply("Ok")])
    client = GeminiClient(api_key="k", client=SimpleNamespace(models=models), sleep=waits.append)
    client.generate("Hello")
    assert waits[0] >= 7


def test_server_error_is_retried_then_raised():
    client, models = make_client(*[api_error(503, "UNAVAILABLE") for _ in range(4)], max_retries=3)
    with pytest.raises(ProviderError) as info:
        client.generate("Hello")
    assert len(models.calls) == 4
    assert info.value.status_code == 503


@pytest.mark.parametrize("code", [400, 403])
def test_client_errors_are_not_retried(code):
    client, models = make_client(api_error(code, message="Nope"))
    with pytest.raises(ProviderError) as info:
        client.generate("Hello")
    assert len(models.calls) == 1
    assert info.value.status_code == code


def test_invalid_key_gets_a_clear_message():
    client, _ = make_client(api_error(400, "INVALID_ARGUMENT", "API key not valid."))
    with pytest.raises(ProviderError) as info:
        client.generate("Hello")
    assert "GEMINI_API_KEY" in info.value.user_message


def test_unknown_model_gets_a_clear_message():
    client, _ = make_client(api_error(404, "NOT_FOUND", "models/x is not found"))
    with pytest.raises(ProviderError) as info:
        client.generate("Hello")
    assert "GEMINI_MODEL" in info.value.user_message


def test_timeout_is_retried():
    client, models = make_client(httpx.ReadTimeout("slow"), reply("Finally"))
    assert client.generate("Hello") == "Finally"
    assert len(models.calls) == 2


def test_timeout_every_time_raises_provider_error():
    client, _ = make_client(*[httpx.ReadTimeout("slow") for _ in range(2)], max_retries=1)
    with pytest.raises(ProviderError) as info:
        client.generate("Hello")
    assert "too long" in info.value.user_message


def test_blocked_answer_raises_provider_error():
    blocked = SimpleNamespace(
        text=None, prompt_feedback=SimpleNamespace(block_reason="SAFETY"), candidates=[]
    )
    client, models = make_client(blocked)
    with pytest.raises(ProviderError) as info:
        client.generate("Hello")
    assert "SAFETY" in str(info.value)
    assert len(models.calls) == 1


def test_stream_yields_chunks_in_order():
    client, _ = make_client(["The ", "", "answer"])
    assert list(client.stream("Hello", system="Be brief.")) == ["The ", "answer"]


def test_stream_retries_error_before_first_chunk():
    client, models = make_client(rate_limited(), ["Hi"])
    assert list(client.stream("Hello")) == ["Hi"]
    assert len(models.calls) == 2


def test_stream_error_after_first_chunk_is_not_retried():
    client, models = make_client(["Partial", api_error(503, "UNAVAILABLE")])
    received = []
    with pytest.raises(ProviderError):
        for piece in client.stream("Hello"):
            received.append(piece)
    assert received == ["Partial"]
    assert len(models.calls) == 1


def test_empty_stream_raises_provider_error():
    client, _ = make_client([""])
    with pytest.raises(ProviderError):
        list(client.stream("Hello"))
