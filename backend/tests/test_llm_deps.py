import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_llm_client
from app.config import settings
from app.llm.errors import MissingAPIKeyError
from app.main import app


@pytest.fixture
def no_key(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "")
    get_llm_client.cache_clear()
    yield
    get_llm_client.cache_clear()


def test_app_starts_without_api_key(no_key):
    # No `with`: skips the startup hook, which would touch the real database.
    response = TestClient(app).get("/health")
    assert response.status_code == 200


def test_llm_client_fails_only_when_used(no_key):
    with pytest.raises(MissingAPIKeyError):
        get_llm_client()
