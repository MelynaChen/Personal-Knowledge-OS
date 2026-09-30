import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.config.settings import get_settings
from app.database.base import Base
from app.database.engine import make_engine
from app.database.session import get_session
from app.main import app


@pytest.fixture
def web_client(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'web.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)

    def override_session():
        with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        yield TestClient(app), sessions
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def payload_for_today(sample_payload):
    payload = json.loads(json.dumps(sample_payload, ensure_ascii=False))
    payload["date"] = datetime.now(ZoneInfo(get_settings().app_timezone)).date().isoformat()
    return payload


def import_payload(client, payload):
    raw_text = json.dumps(payload, ensure_ascii=False)
    preview = client.post("/import/preview", json={"raw_text": raw_text})
    assert preview.status_code == 200
    committed = client.post("/import/commit", json={
        "raw_text": raw_text, "preview_hash": preview.json()["preview_hash"]})
    assert committed.status_code == 202
    return committed.json()["import_id"]


def test_daily_pages_render_and_keep_existing_api(web_client):
    client, _ = web_client
    for path in ("/", "/import", "/history", "/knowledge", "/reviews", "/prompt", "/system"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert "Personal Knowledge OS" in response.text
    assert client.get("/static/app.css").status_code == 200
    assert client.get("/static/import.js").status_code == 200
    assert client.get("/health").json() == {"status": "ok", "phase": 2}
    assert client.get("/openapi.json").status_code == 200


def test_import_preview_commit_and_history_ui(web_client, sample_payload):
    client, _ = web_client
    assert "Commit &amp; Sync" in client.get("/import").text
    payload = payload_for_today(sample_payload)
    import_id = import_payload(client, payload)
    assert client.get(f"/history/{import_id}").status_code == 200
    assert "学习 RAG 中的 Embedding" in client.get("/history").text
    assert "学习 RAG 中的 Embedding" in client.get("/").text
    raw_text = json.dumps(payload, ensure_ascii=False)
    assert client.post("/import/preview", json={"raw_text": raw_text}).json()["items"][0]["status"] == "duplicate"


def test_knowledge_tree_and_prompt_context_stable(web_client, sample_payload):
    client, _ = web_client
    import_payload(client, payload_for_today(sample_payload))
    tree = client.get("/knowledge")
    assert tree.status_code == 200
    assert "Embedding" in tree.text and "Tasks" in tree.text
    first = client.get("/api/knowledge/prompt-context").json()["tree_text"]
    second = client.get("/api/knowledge/prompt-context").json()["tree_text"]
    assert first == second
    assert "AI\n└── LLM\n    └── RAG\n        └── Embedding" in first
    assert "node_key" not in first and "notion" not in first.lower()
    assert first in client.get("/prompt").text


def test_reviews_ui_uses_existing_complete_api(web_client, sample_payload):
    client, _ = web_client
    import_payload(client, payload_for_today(sample_payload))
    due = client.get("/reviews/today").json()
    assert len(due) == 1
    response = client.get("/reviews")
    assert response.status_code == 200 and "比较模糊" in response.text
    result = client.post(f"/reviews/{due[0]['id']}/complete", json={
        "memory_score": 3, "request_key": "web-review-test", "expected_version": due[0]["version"]})
    assert result.status_code == 200
    assert result.json()["new_level"] == 1
    assert client.get("/reviews/today").json() == []


def test_task_status_and_detail_pages(web_client, sample_payload):
    client, _ = web_client
    import_id = import_payload(client, payload_for_today(sample_payload))
    task_id = client.get(f"/imports/{import_id}").json()["items"][0]["task_id"]
    task_page = client.get(f"/tasks/{task_id}/view")
    assert task_page.status_code == 200 and "Not started" in task_page.text
    assert client.patch(f"/tasks/{task_id}/status", json={"status": "In progress"}).json()["status"] == "In progress"
    assert "In progress" in client.get(f"/tasks/{task_id}/view").text
    assert client.patch(f"/tasks/{task_id}/status", json={"status": "invalid"}).status_code == 422
    assert client.get("/notes/1/view").status_code == 200
    assert client.get("/knowledge/1/view").status_code == 200


def test_html_escaping_and_friendly_errors(web_client, sample_payload):
    client, _ = web_client
    payload = payload_for_today(sample_payload)
    payload["tasks"][0]["note"]["detailed_explanation"] = "【今日新增】\n<script>alert(1)</script>"
    import_id = import_payload(client, payload)
    history = client.get(f"/history/{import_id}").text
    note = client.get("/notes/1/view").text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in history
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in note
    assert "<script>alert(1)</script>" not in history + note
    assert "【今日新增】" in note
    missing = client.get("/tasks/999999/view")
    assert missing.status_code == 404 and "Page not found" in missing.text
    invalid = client.post("/import/preview", json={"raw_text": "not json"})
    assert invalid.status_code == 422 and "Traceback" not in invalid.text


def test_system_page_does_not_include_secret(web_client):
    client, _ = web_client
    response = client.get("/system")
    assert response.status_code == 200
    assert "NOTION_TOKEN" not in response.text
    assert ".env" not in response.text
