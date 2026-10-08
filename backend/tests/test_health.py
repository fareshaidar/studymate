from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

FAKE_KEY = "test-key-not-real-12345"


def health(monkeypatch, key: str):
    # settings, not .env: the test never depends on the real backend/.env.
    monkeypatch.setattr(settings, "gemini_api_key", key)
    # No `with`: skips the startup hook, which would touch the real database.
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    return response


def test_health_reports_a_missing_key(monkeypatch):
    body = health(monkeypatch, "").json()

    assert body["status"] == "ok"
    assert body["llm_configured"] is False


def test_health_reports_a_configured_key_without_revealing_it(monkeypatch):
    response = health(monkeypatch, FAKE_KEY)

    assert response.json()["llm_configured"] is True
    # Not the key, nor any recognisable piece of it.
    assert FAKE_KEY not in response.text
    assert "12345" not in response.text


def test_health_reports_the_upload_limit(monkeypatch):
    monkeypatch.setattr(settings, "max_upload_mb", 7)

    assert health(monkeypatch, "").json()["max_upload_mb"] == 7
