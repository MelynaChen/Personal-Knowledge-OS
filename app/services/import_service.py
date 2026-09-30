from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Task
from app.schemas.common import digest
from app.schemas.import_schema import parse_import


def task_external_id(schema_version: int, day, task) -> str:
    return digest({"version": schema_version, "date": day.isoformat(),
                   "normalized_name": task.name, "normalized_knowledge_path": task.knowledge_path})


def task_content_hash(task) -> str:
    return digest(task.model_dump(mode="json"))


def preview_import(session: Session, raw_text: str) -> dict:
    payload = parse_import(raw_text)
    normalized = payload.model_dump(mode="json")
    identities = [task_external_id(payload.schema_version, payload.date, t) for t in payload.tasks]
    counts = Counter(identities)
    items = []
    for task, external_id in zip(payload.tasks, identities):
        content_hash = task_content_hash(task)
        existing = session.scalar(select(Task).where(Task.external_id == external_id))
        status = ("conflict" if counts[external_id] > 1 else
                  "new" if existing is None else
                  "duplicate" if existing.content_hash == content_hash else "conflict")
        items.append({"task_name": task.name, "knowledge_path": task.knowledge_path,
                      "status": status, "existing_task_id": existing.id if existing else None,
                      "external_id": external_id, "content_hash": content_hash})
    return {"preview_hash": digest(normalized), "payload": normalized, "items": items}
