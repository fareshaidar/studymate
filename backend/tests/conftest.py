import pytest
from google import genai


@pytest.fixture(autouse=True)
def no_real_gemini(monkeypatch):
    """Safety net: any test that tries to create a real Gemini client fails loudly."""

    def refuse(*args, **kwargs):
        raise RuntimeError("Tests must not create a real Gemini client; inject a fake instead.")

    monkeypatch.setattr(genai, "Client", refuse)
