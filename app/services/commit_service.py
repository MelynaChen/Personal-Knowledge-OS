from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ImportItem, ImportRecord, KnowledgeNode, Note, Review, SyncOperation, Task
from app.schemas.common import digest
from app.schemas.import_schema import parse_import
from app.services.import_service import preview_import
from app.services.knowledge_service import get_or_create_knowledge_path


class PreviewMismatch(ValueError):
    pass


class ImportConflict(ValueError):
    pass


def enqueue(session: Session, object_type: str, local_id: int, step: str,
            dependency: SyncOperation | None = None, version: int = 1) -> SyncOperation:
    key = f"{object_type}:{local_id}:{version}:{step}"
    operation = session.scalar(select(SyncOperation).where(SyncOperation.operation_key == key))
    if operation is None:
        operation = SyncOperation(operation_key=key, object_type=object_type, local_id=local_id,
                                  object_version=version, step=step, request_json=None,
                                  depends_on_id=dependency.id if dependency else None,
                                  status="pending", attempts=0)
        session.add(operation)
        session.flush()
    return operation


def commit_import(session: Session, raw_text: str, preview_hash: str) -> ImportRecord:
    """Caller owns a single SQLite transaction. No Notion calls occur here."""
    preview = preview_import(session, raw_text)
    if preview["preview_hash"] != preview_hash:
        raise PreviewMismatch("preview_hash does not match the normalized input")
    if any(item["status"] == "conflict" for item in preview["items"]):
        raise ImportConflict("task identity conflicts with existing or repeated content")
    payload = parse_import(raw_text)
    record = ImportRecord(raw_text=raw_text, normalized_json=preview["payload"],
                          content_hash=preview_hash, schema_version=payload.schema_version,
                          status="pending" if any(i["status"] == "new" for i in preview["items"]) else "completed")
    session.add(record)
    session.flush()
    for index, (source, item) in enumerate(zip(payload.tasks, preview["items"])):
        if item["status"] == "duplicate":
            session.add(ImportItem(import_id=record.id, item_index=index, task_id=item["existing_task_id"],
                                   status="duplicate", result_json={"external_id": item["external_id"]}))
            continue
        leaf = get_or_create_knowledge_path(session, source.knowledge_path, source.category)
        ancestors: list[KnowledgeNode] = []
        node = leaf
        while node is not None:
            ancestors.append(node)
            node = session.get(KnowledgeNode, node.parent_id) if node.parent_id else None
        dependency = None
        for node in reversed(ancestors):
            dependency = enqueue(session, "knowledge", node.id, "CREATE_KNOWLEDGE_PAGE", dependency)
        task = Task(external_id=item["external_id"], date=payload.date, name=source.name,
                    category=source.category, priority=source.priority, learning_goal=source.learning_goal,
                    action_steps_json=source.action_steps, output_required=source.output_required,
                    knowledge_node_id=leaf.id, content_hash=item["content_hash"])
        session.add(task)
        session.flush()
        task_page = enqueue(session, "task", task.id, "CREATE_TASK_PAGE", dependency)
        task_blocks = enqueue(session, "task", task.id, "WRITE_TASK_BLOCKS", task_page)
        note_external_id = digest({"task": task.external_id, "role": "note"})
        note = Note(external_id=note_external_id, task_id=task.id, knowledge_node_id=leaf.id,
                    date=payload.date, title=source.note.title, summary=source.note.summary,
                    content_json=source.note.model_dump(mode="json"),
                    content_hash=digest(source.note.model_dump(mode="json")))
        session.add(note)
        session.flush()
        note_page = enqueue(session, "note", note.id, "CREATE_NOTE_PAGE", task_blocks)
        note_blocks = enqueue(session, "note", note.id, "WRITE_NOTE_BLOCKS", note_page)
        final = note_blocks
        if source.review.enabled:
            review = Review(external_id=digest({"note": note_external_id, "role": "review"}),
                            note_id=note.id, task_id=task.id, knowledge_node_id=leaf.id,
                            initial_learning_date=payload.date, review_level=0,
                            next_review_date=payload.date, status="Scheduled", difficulty=source.review.difficulty,
                            memory_score=None, version=0, algorithm_version="v1", algorithm_config_json={})
            session.add(review)
            session.flush()
            final = enqueue(session, "review", review.id, "CREATE_REVIEW_PAGE", note_blocks)
        enqueue(session, "task", task.id, "VERIFY_OBJECT", final)
        session.add(ImportItem(import_id=record.id, item_index=index, task_id=task.id,
                               status="saved", result_json={"external_id": task.external_id}))
    return record
