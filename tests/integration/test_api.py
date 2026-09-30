import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from app.main import app


def test_health_and_home():
    client = TestClient(app)
    assert client.get("/health").json() == {"status": "ok", "phase": 2}
    assert "Personal Knowledge OS" in client.get("/").text


def test_preview_invalid_input():
    client = TestClient(app)
    result = client.post("/import/preview", json={"raw_text": "not json"})
    assert result.status_code == 422
