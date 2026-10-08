from fastapi.testclient import TestClient

from app.api.deps import get_llm_client
from app.main import app


def test_an_unexpected_error_is_a_friendly_json_500():
    def broken():
        raise RuntimeError("secret internal detail: /home/app/data/studymate.db")

    # Any route works: an exception nothing else handles reaches the catch-all.
    app.dependency_overrides[get_llm_client] = broken
    try:
        # raise_server_exceptions=False: get the response a browser would get.
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/chat", json={"question": "How do GAs work?"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 500
    assert response.json() == {
        "detail": "Something went wrong on the server. Please try again.",
        "code": "internal_error",
    }
    # Nothing about the cause reaches the client.
    assert "secret" not in response.text and "RuntimeError" not in response.text
