import json

from sqlalchemy import func, select

from app.models import KnowledgeNode, Note, Review, Task
from app.schemas.import_schema import parse_import
from app.services.import_service import preview_import
from app.services.knowledge_service import get_or_create_knowledge_path


def insert_task(session, sample_json, content_hash=None):
    result = preview_import(session, sample_json)
    item = result["items"][0]
    payload = parse_import(sample_json)
    node = get_or_create_knowledge_path(session, payload.tasks[0].knowledge_path)
    task = payload.tasks[0]
    row = Task(external_id=item["external_id"], date=payload.date, name=task.name,
               category=task.category, priority=task.priority, learning_goal=task.learning_goal,
               action_steps_json=task.action_steps, output_required=task.output_required,
               knowledge_node_id=node.id, content_hash=content_hash or item["content_hash"])
    session.add(row)
    session.commit()


def test_preview_new(session, sample_json):
    result = preview_import(session, sample_json)
    assert result["items"][0]["status"] == "new"
    assert len(result["preview_hash"]) == 64


def test_preview_duplicate(session, sample_json):
    insert_task(session, sample_json)
    assert preview_import(session, sample_json)["items"][0]["status"] == "duplicate"


def test_preview_conflict(session, sample_json):
    insert_task(session, sample_json, "0" * 64)
    assert preview_import(session, sample_json)["items"][0]["status"] == "conflict"


def test_preview_does_not_write_database(session, sample_json):
    before = [session.scalar(select(func.count()).select_from(model)) for model in (Task, Note, Review, KnowledgeNode)]
    preview_import(session, sample_json)
    after = [session.scalar(select(func.count()).select_from(model)) for model in (Task, Note, Review, KnowledgeNode)]
    assert before == after == [0, 0, 0, 0]
