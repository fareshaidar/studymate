import pytest

from app.llm.base import LLMClient
from app.llm.errors import RateLimitError
from tests.fakes import FakeLLMClient


def test_fake_is_an_llm_client():
    assert isinstance(FakeLLMClient(), LLMClient)


def test_generate_returns_reply_and_records_call():
    fake = FakeLLMClient(reply="42")
    assert fake.generate("What is the answer?", system="Be brief.") == "42"
    assert fake.calls == [("What is the answer?", "Be brief.")]


def test_stream_yields_chunks():
    fake = FakeLLMClient(chunks=["Hel", "lo"])
    assert list(fake.stream("Hi")) == ["Hel", "lo"]
    assert fake.calls == [("Hi", None)]


def test_can_simulate_errors():
    fake = FakeLLMClient(error=RateLimitError())
    with pytest.raises(RateLimitError):
        fake.generate("Hi")
    with pytest.raises(RateLimitError):
        list(fake.stream("Hi"))
