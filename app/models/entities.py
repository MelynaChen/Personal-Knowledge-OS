from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TimeMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class ImportRecord(Base, TimeMixin):
    __tablename__ = "imports"
    id: Mapped[int] = mapped_column(primary_key=True)
    raw_text: Mapped[str] = mapped_column(Text)
    normalized_json: Mapped[dict] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    schema_version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ImportItem(Base):
    __tablename__ = "import_items"
    __table_args__ = (UniqueConstraint("import_id", "item_index"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    import_id: Mapped[int] = mapped_column(ForeignKey("imports.id"), index=True)
    item_index: Mapped[int] = mapped_column(Integer)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"))
    status: Mapped[str] = mapped_column(String(20))
    result_json: Mapped[dict | None] = mapped_column(JSON)


class KnowledgeNode(Base, TimeMixin):
    __tablename__ = "knowledge_nodes"
    __table_args__ = (
        UniqueConstraint("parent_id", "normalized_name", name="uq_knowledge_child"),
        Index("uq_knowledge_root", "normalized_name", unique=True, sqlite_where=text("parent_id IS NULL")),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("knowledge_nodes.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    normalized_name: Mapped[str] = mapped_column(String(200))
    path_json: Mapped[list] = mapped_column(JSON)
    display_path: Mapped[str] = mapped_column(Text)
    level: Mapped[int] = mapped_column(Integer)
    node_key: Mapped[str] = mapped_column(String(64), unique=True)
    category: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="")


class Task(Base, TimeMixin):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(64), unique=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(100))
    priority: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="Not started", nullable=False)
    learning_goal: Mapped[str] = mapped_column(Text)
    action_steps_json: Mapped[list] = mapped_column(JSON)
    output_required: Mapped[str] = mapped_column(Text)
    knowledge_node_id: Mapped[int] = mapped_column(ForeignKey("knowledge_nodes.id"), index=True)
    content_hash: Mapped[str] = mapped_column(String(64))


class Note(Base, TimeMixin):
    __tablename__ = "notes"
    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(64), unique=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), unique=True)
    knowledge_node_id: Mapped[int] = mapped_column(ForeignKey("knowledge_nodes.id"), index=True)
    date: Mapped[date] = mapped_column(Date)
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(Text)
    content_json: Mapped[dict] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64))


class Review(Base, TimeMixin):
    __tablename__ = "reviews"
    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(64), unique=True)
    note_id: Mapped[int] = mapped_column(ForeignKey("notes.id"), unique=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    knowledge_node_id: Mapped[int] = mapped_column(ForeignKey("knowledge_nodes.id"), index=True)
    initial_learning_date: Mapped[date] = mapped_column(Date)
    review_level: Mapped[int] = mapped_column(Integer, default=0)
    next_review_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(20), default="Scheduled")
    difficulty: Mapped[str] = mapped_column(String(20))
    memory_score: Mapped[int | None] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer, default=0)
    algorithm_version: Mapped[str] = mapped_column(String(20), default="v1")
    algorithm_config_json: Mapped[dict] = mapped_column(JSON)


class ReviewEvent(Base):
    __tablename__ = "review_events"
    __table_args__ = (UniqueConstraint("review_id", "request_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    review_id: Mapped[int] = mapped_column(ForeignKey("reviews.id"), index=True)
    request_key: Mapped[str] = mapped_column(String(200))
    memory_score: Mapped[int] = mapped_column(Integer)
    old_level: Mapped[int] = mapped_column(Integer)
    new_level: Mapped[int] = mapped_column(Integer)
    old_next_review_date: Mapped[date] = mapped_column(Date)
    new_next_review_date: Mapped[date] = mapped_column(Date)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    algorithm_version: Mapped[str] = mapped_column(String(20))


class NotionObject(Base, TimeMixin):
    __tablename__ = "notion_objects"
    __table_args__ = (UniqueConstraint("object_type", "local_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    object_type: Mapped[str] = mapped_column(String(30))
    local_id: Mapped[int] = mapped_column(Integer)
    external_id: Mapped[str] = mapped_column(String(64), index=True)
    notion_page_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    data_source_id: Mapped[str | None] = mapped_column(String(64))
    body_block_id: Mapped[str | None] = mapped_column(String(64))
    remote_edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sync_version: Mapped[int] = mapped_column(Integer, default=0)
    synced_content_hash: Mapped[str | None] = mapped_column(String(64))


class NotionDatabase(Base, TimeMixin):
    __tablename__ = "notion_databases"
    id: Mapped[int] = mapped_column(primary_key=True)
    logical_name: Mapped[str] = mapped_column(String(40), unique=True)
    database_id: Mapped[str | None] = mapped_column(String(64))
    data_source_id: Mapped[str | None] = mapped_column(String(64))
    property_ids_json: Mapped[dict] = mapped_column(JSON, default=dict)
    init_step: Mapped[str] = mapped_column(String(40), default="pending")
    schema_version: Mapped[int] = mapped_column(Integer, default=1)


class SyncOperation(Base, TimeMixin):
    __tablename__ = "sync_operations"
    id: Mapped[int] = mapped_column(primary_key=True)
    operation_key: Mapped[str] = mapped_column(String(150), unique=True)
    object_type: Mapped[str] = mapped_column(String(30))
    local_id: Mapped[int] = mapped_column(Integer)
    object_version: Mapped[int] = mapped_column(Integer)
    step: Mapped[str] = mapped_column(String(50))
    request_json: Mapped[dict | None] = mapped_column(JSON)
    depends_on_id: Mapped[int | None] = mapped_column(ForeignKey("sync_operations.id"))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result_json: Mapped[dict | None] = mapped_column(JSON)
    last_error: Mapped[str | None] = mapped_column(Text)


class SyncLog(Base):
    __tablename__ = "sync_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    operation_id: Mapped[int | None] = mapped_column(ForeignKey("sync_operations.id"))
    error_category: Mapped[str] = mapped_column(String(50))
    http_status: Mapped[int | None] = mapped_column(Integer)
    notion_request_id: Mapped[str | None] = mapped_column(String(100))
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value_json: Mapped[dict] = mapped_column(JSON)
