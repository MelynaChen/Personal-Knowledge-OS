"""At-least-once operation runner with remote reconciliation before every create."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select, update

from app.config.settings import get_settings
from app.database.session import SessionLocal
from app.models import (ImportItem, ImportRecord, KnowledgeNode, Note, NotionDatabase,
                        NotionObject, Review, SyncLog, SyncOperation, Task)
from app.notion.blocks import (CONTAINER_MARKER, block_batches, container_block,
                               note_blocks, task_blocks)
from app.notion.client import (NotionFailure, NotionGateway, RemoteConflict,
                               UnknownWriteResult)
from app.notion.databases import SchemaMismatch, verify_notion_schema
from app.notion.pagination import paginated
from app.notion.properties import (knowledge_properties, note_properties,
                                   review_properties, task_properties)
from app.schemas.common import digest

log = logging.getLogger(__name__)
TYPE_TO_DB = {"knowledge": "knowledge_tree", "task": "daily_tasks",
              "note": "notes", "review": "review_queue"}
TYPE_TO_MODEL = {"knowledge": KnowledgeNode, "task": Task, "note": Note, "review": Review}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _text(block: dict) -> str:
    item = block.get(block.get("type"), {})
    return "".join(x.get("plain_text", x.get("text", {}).get("content", ""))
                   for x in item.get("rich_text", []))


class SyncWorker:
    def __init__(self, session_factory=SessionLocal, gateway=None, *, check_schema=True):
        self.sessions = session_factory
        self.gateway = gateway or NotionGateway()
        self.settings = self.gateway.settings
        self.check_schema = check_schema
        self._verified = False

    def _schema(self):
        if self.check_schema and not self._verified:
            verify_notion_schema(self.sessions, self.gateway)
            self._verified = True

    def claim(self) -> int | None:
        now = _now()
        with self.sessions.begin() as session:
            candidates = session.scalars(select(SyncOperation).where(
                or_(SyncOperation.status == "pending",
                    (SyncOperation.status == "processing") & (SyncOperation.lease_until < now)),
                or_(SyncOperation.next_attempt_at.is_(None), SyncOperation.next_attempt_at <= now))
                .order_by(SyncOperation.id).limit(100)).all()
            for op in candidates:
                if op.depends_on_id and session.get(SyncOperation, op.depends_on_id).status != "completed":
                    continue
                result = session.execute(update(SyncOperation).where(
                    SyncOperation.id == op.id, SyncOperation.status == op.status)
                    .values(status="processing", attempts=op.attempts + 1,
                            lease_until=now + timedelta(minutes=5)))
                if result.rowcount == 1:
                    return op.id
        return None

    def run_once(self, limit: int | None = None) -> int:
        self._schema()
        count = 0
        for _ in range(limit or self.settings.sync_worker_batch_size):
            op_id = self.claim()
            if op_id is None:
                break
            self.execute(op_id)
            count += 1
        return count

    def execute(self, op_id: int) -> None:
        try:
            with self.sessions() as session:
                op = session.get(SyncOperation, op_id)
                self._perform(session, op)
            with self.sessions.begin() as session:
                op = session.get(SyncOperation, op_id)
                op.status = "completed"
                op.lease_until = None
                op.next_attempt_at = None
                op.last_error = None
                self._refresh_imports(session, op)
        except (NotionFailure, SchemaMismatch, ValueError, KeyError) as exc:
            self._failure(op_id, exc)

    def _failure(self, op_id: int, exc: Exception) -> None:
        kind = exc.kind if isinstance(exc, NotionFailure) else "schema" if isinstance(exc, SchemaMismatch) else "validation"
        retryable = kind in ("rate_limited", "server", "transport") or isinstance(exc, UnknownWriteResult)
        with self.sessions.begin() as session:
            op = session.get(SyncOperation, op_id)
            op.status = "pending" if retryable else "failed"
            op.last_error = str(exc)[:1000]
            op.lease_until = None
            if retryable:
                delay = exc.retry_after if isinstance(exc, NotionFailure) and exc.retry_after else min(2 ** min(op.attempts, 8), 300)
                op.next_attempt_at = _now() + timedelta(seconds=delay)
            session.add(SyncLog(operation_id=op_id, error_category=kind,
                                http_status=exc.status if isinstance(exc, NotionFailure) else None,
                                notion_request_id=exc.request_id if isinstance(exc, NotionFailure) else None,
                                message=str(exc)[:1000]))
            self._refresh_imports(session, op)
        log.warning("sync operation=%s kind=%s attempt=%s", op_id, kind, op.attempts)

    def _db_id(self, session, object_type: str) -> str:
        row = session.scalar(select(NotionDatabase).where(NotionDatabase.logical_name == TYPE_TO_DB[object_type]))
        if not row or not row.data_source_id or row.init_step != "completed":
            raise SchemaMismatch([f"{TYPE_TO_DB[object_type]} is not initialized"])
        return row.data_source_id

    def _mapped_page(self, session, object_type: str, local_id: int) -> str:
        row = session.scalar(select(NotionObject).where(NotionObject.object_type == object_type,
                                                       NotionObject.local_id == local_id))
        if not row or not row.notion_page_id:
            raise ValueError(f"missing {object_type} page for local id {local_id}")
        return row.notion_page_id

    def _properties(self, session, object_type, obj):
        if object_type == "knowledge":
            if obj.parent_id == obj.id:
                raise ValueError("knowledge node cannot parent itself")
            return knowledge_properties(obj, self._mapped_page(session, "knowledge", obj.parent_id) if obj.parent_id else None)
        if object_type == "task":
            return task_properties(obj, self._mapped_page(session, "knowledge", obj.knowledge_node_id))
        if object_type == "note":
            return note_properties(obj, self._mapped_page(session, "knowledge", obj.knowledge_node_id),
                                   self._mapped_page(session, "task", obj.task_id))
        return review_properties(obj, self._mapped_page(session, "knowledge", obj.knowledge_node_id),
                                 self._mapped_page(session, "note", obj.note_id),
                                 self._mapped_page(session, "task", obj.task_id))

    def _create(self, session, op, obj):
        data_source_id = self._db_id(session, op.object_type)
        external_id = obj.node_key if op.object_type == "knowledge" else obj.external_id
        mapping = session.scalar(select(NotionObject).where(NotionObject.object_type == op.object_type,
                                                            NotionObject.local_id == op.local_id))
        if mapping and mapping.notion_page_id:
            return
        remote = list(paginated(self.gateway.query_data_source, data_source_id=data_source_id,
                                filter={"property": "External ID", "rich_text": {"equals": external_id}}))
        if len(remote) > 1:
            raise RemoteConflict("remote_conflict")
        if remote:
            page = remote[0]
        else:
            # An uncertain POST is reconciled twice, on separate scheduled attempts.
            uncertainty = (op.result_json or {}).get("uncertain_checks", 0)
            if uncertainty == 1:
                self._save_result(op.id, {"uncertain_checks": 2})
                raise UnknownWriteResult("transport")
            try:
                page = self.gateway.create_page(parent={"type": "data_source_id", "data_source_id": data_source_id},
                                                properties=self._properties(session, op.object_type, obj))
            except UnknownWriteResult:
                self._save_result(op.id, {"uncertain_checks": 1})
                raise
        with self.sessions.begin() as write_session:
            mapped = write_session.scalar(select(NotionObject).where(NotionObject.object_type == op.object_type,
                                                                      NotionObject.local_id == op.local_id))
            if mapped is None:
                mapped = NotionObject(object_type=op.object_type, local_id=op.local_id,
                                      external_id=external_id, data_source_id=data_source_id)
                write_session.add(mapped)
            mapped.notion_page_id = page["id"]
            mapped.remote_edited_at = datetime.fromisoformat(page["last_edited_time"].replace("Z", "+00:00")) if page.get("last_edited_time") else None
            mapped.sync_version = op.object_version

    def _save_result(self, op_id: int, result: dict) -> None:
        with self.sessions.begin() as session:
            session.get(SyncOperation, op_id).result_json = result

    def _write_blocks(self, session, op, obj):
        mapping = session.scalar(select(NotionObject).where(NotionObject.object_type == op.object_type,
                                                            NotionObject.local_id == op.local_id))
        if not mapping or not mapping.notion_page_id:
            raise ValueError("page mapping missing before body write")
        if mapping.synced_content_hash == obj.content_hash:
            return
        if mapping.synced_content_hash and mapping.synced_content_hash != obj.content_hash:
            raise ValueError("needs_update: immutable first-write content changed")
        if mapping.body_block_id:
            container_id = mapping.body_block_id
        else:
            containers = [b for b in paginated(self.gateway.list_children, block_id=mapping.notion_page_id)
                          if b.get("type") == "toggle" and _text(b) == CONTAINER_MARKER]
            if len(containers) > 1:
                raise RemoteConflict("duplicate_body_container")
            if containers:
                container_id = containers[0]["id"]
            else:
                response = self.gateway.append_children(mapping.notion_page_id, [container_block()])
                container_id = response["results"][0]["id"]
            with self.sessions.begin() as write_session:
                row = write_session.scalar(select(NotionObject).where(NotionObject.object_type == op.object_type,
                                                                       NotionObject.local_id == op.local_id))
                row.body_block_id = container_id
        blocks = task_blocks(obj, session.get(KnowledgeNode, obj.knowledge_node_id).path_json) if op.object_type == "task" else note_blocks(obj)
        batches = block_batches(blocks, obj.content_hash)
        for index, batch in enumerate(batches):
            marker = f"PKOS:BATCH:{obj.content_hash}:{index}"
            existing = [b for b in paginated(self.gateway.list_children, block_id=container_id)
                        if b.get("type") == "paragraph" and _text(b) == marker]
            if len(existing) > 1:
                raise RemoteConflict("duplicate_body_batch")
            if not existing:
                self.gateway.append_children(container_id, batch)
        with self.sessions.begin() as write_session:
            row = write_session.scalar(select(NotionObject).where(NotionObject.object_type == op.object_type,
                                                                   NotionObject.local_id == op.local_id))
            row.synced_content_hash = obj.content_hash

    def _perform(self, session, op):
        if op.step == "VERIFY_OBJECT":
            page_id = self._mapped_page(session, "task", op.local_id)
            if self.gateway.retrieve_page(page_id).get("id") != page_id:
                raise ValueError("remote task verification failed")
            return
        obj = session.get(TYPE_TO_MODEL[op.object_type], op.local_id)
        if obj is None:
            raise ValueError("local object missing")
        if op.step.startswith("CREATE_"):
            self._create(session, op, obj)
        elif op.step in ("WRITE_TASK_BLOCKS", "WRITE_NOTE_BLOCKS"):
            self._write_blocks(session, op, obj)
        else:
            raise ValueError(f"unknown operation {op.step}")

    def _refresh_imports(self, session, op):
        task_ids = []
        if op.object_type == "task":
            task_ids = [op.local_id]
        elif op.object_type == "note":
            note = session.get(Note, op.local_id)
            task_ids = [note.task_id] if note else []
        elif op.object_type == "review":
            review = session.get(Review, op.local_id)
            task_ids = [review.task_id] if review else []
        elif op.object_type == "knowledge":
            task_ids = list(session.scalars(select(Task.id).where(Task.knowledge_node_id == op.local_id)))
        for task_id in task_ids:
            for item in session.scalars(select(ImportItem).where(ImportItem.task_id == task_id)):
                record = session.get(ImportRecord, item.import_id)
                task_ops = list(session.scalars(select(SyncOperation).where(SyncOperation.object_type == "task",
                                                                         SyncOperation.local_id == task_id)))
                if any(x.status == "failed" for x in task_ops):
                    record.status = "failed"
                elif any(x.step == "VERIFY_OBJECT" and x.status == "completed" for x in task_ops):
                    item.status = "completed"
                    items = list(session.scalars(select(ImportItem).where(ImportItem.import_id == record.id)))
                    if all(x.status in ("completed", "duplicate") for x in items):
                        record.status = "completed"
                        record.completed_at = _now()
                elif record.status != "failed":
                    record.status = "processing"


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    worker = SyncWorker()
    log.info("sync worker started poll_interval=%ss batch_size=%s",
             worker.settings.sync_worker_poll_seconds, worker.settings.sync_worker_batch_size)
    while True:
        worker.run_once()
        time.sleep(worker.settings.sync_worker_poll_seconds)


if __name__ == "__main__":
    main()
