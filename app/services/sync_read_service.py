"""Read-only sync status shared by API and web pages."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Note, Review, SyncOperation


def item_operations(session: Session, task_id: int) -> list[SyncOperation]:
    note = session.scalar(select(Note).where(Note.task_id == task_id))
    review = session.scalar(select(Review).where(Review.task_id == task_id))
    keys = [("task", task_id)]
    if note:
        keys.append(("note", note.id))
    if review:
        keys.append(("review", review.id))
    operations = []
    for kind, local_id in keys:
        operations.extend(session.scalars(select(SyncOperation).where(
            SyncOperation.object_type == kind, SyncOperation.local_id == local_id)).all())
    by_id = {op.id: op for op in operations}
    for op in list(operations):
        parent_id = op.depends_on_id
        while parent_id and parent_id not in by_id:
            parent = session.get(SyncOperation, parent_id)
            if parent is None:
                break
            by_id[parent.id] = parent
            parent_id = parent.depends_on_id
    return list(by_id.values())


def task_sync_status(session: Session, task_id: int) -> str:
    operations = item_operations(session, task_id)
    if not operations:
        return "local only"
    if any(op.status == "failed" for op in operations):
        return "failed"
    if any(op.step == "VERIFY_OBJECT" and op.status == "completed" for op in operations):
        return "completed"
    if any(op.status == "processing" for op in operations):
        return "processing"
    return "pending"
