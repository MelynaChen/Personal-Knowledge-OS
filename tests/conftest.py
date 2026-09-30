import json
from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.database.base import Base
from app.database.engine import make_engine


def pytest_configure(config):
    if config.option.basetemp is None:
        root = Path(__file__).resolve().parent / ".tmp"
        root.mkdir(parents=True, exist_ok=True)
        config.option.basetemp = str(root / f"run-{uuid4().hex}")


@pytest.fixture
def session(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


@pytest.fixture
def sample_payload():
    return {"date": "2026-09-29", "tasks": [{
        "name": "学习 RAG 中的 Embedding", "category": "AI", "priority": "High",
        "knowledge_path": ["AI", "LLM", "RAG", "Embedding"],
        "learning_goal": "理解作用", "action_steps": ["学习概念"],
        "output_required": "笔记", "note": {"title": "Embedding", "summary": "摘要",
        "key_concepts": [], "detailed_explanation": "正文", "examples": [], "practice": [],
        "my_understanding": "", "questions": [], "common_mistakes": [],
        "next_topics": [], "resources": []},
        "review": {"enabled": True, "difficulty": "Medium"}}]}


@pytest.fixture
def sample_json(sample_payload):
    return json.dumps(sample_payload, ensure_ascii=False)
