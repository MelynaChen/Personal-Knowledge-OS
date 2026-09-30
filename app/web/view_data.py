"""Read-only presentation queries; no Notion calls or business mutations."""
from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.models import (ImportItem, ImportRecord, KnowledgeNode, Note, NotionObject,
                        Review, ReviewEvent, SyncLog, SyncOperation, Task)
from app.services.sync_read_service import item_operations, task_sync_status


def today_date():
    return datetime.now(ZoneInfo(get_settings().app_timezone)).date()


def notion_page_url(page_id: str | None) -> str | None:
    if page_id and re.fullmatch(r"[0-9a-fA-F-]{32,36}", page_id):
        return f"https://www.notion.so/{page_id.replace('-', '')}"
    return None


def mapping_for(session: Session, object_type: str, local_id: int) -> NotionObject | None:
    return session.scalar(select(NotionObject).where(NotionObject.object_type == object_type,
                                                    NotionObject.local_id == local_id))


def task_view(session: Session, task: Task) -> dict:
    node = session.get(KnowledgeNode, task.knowledge_node_id)
    note = session.scalar(select(Note).where(Note.task_id == task.id))
    review = session.scalar(select(Review).where(Review.task_id == task.id))
    mapping = mapping_for(session, "task", task.id)
    return {"task": task, "node": node, "note": note, "review": review,
            "sync_status": task_sync_status(session, task.id), "mapping": mapping,
            "notion_url": notion_page_url(mapping.notion_page_id) if mapping else None}


def dashboard_data(session: Session) -> dict:
    day = today_date()
    tasks = list(session.scalars(select(Task).where(Task.date == day).order_by(Task.id.desc())))
    due_count = session.scalar(select(func.count()).select_from(Review).where(
        Review.status == "Scheduled", Review.next_review_date <= day)) or 0
    failed_count = session.scalar(select(func.count()).select_from(SyncOperation).where(
        SyncOperation.status == "failed")) or 0
    reviews = review_groups(session)
    return {"day": day, "task_count": len(tasks), "due_count": due_count,
            "failed_count": failed_count, "tasks": [task_view(session, task) for task in tasks],
            "reviews": reviews["overdue"] + reviews["today"]}


def review_groups(session: Session) -> dict[str, list[dict]]:
    day = today_date()
    groups = {"overdue": [], "today": [], "upcoming": []}
    reviews = session.scalars(select(Review).where(Review.status == "Scheduled")
                              .order_by(Review.next_review_date, Review.id))
    for review in reviews:
        note = session.get(Note, review.note_id)
        node = session.get(KnowledgeNode, review.knowledge_node_id)
        row = {"review": review, "note": note, "node": node}
        key = "overdue" if review.next_review_date < day else "today" if review.next_review_date == day else "upcoming"
        groups[key].append(row)
    return groups


def history_rows(session: Session, limit: int = 100) -> list[dict]:
    rows = []
    records = session.scalars(select(ImportRecord).order_by(ImportRecord.created_at.desc(),
                                                            ImportRecord.id.desc()).limit(limit))
    for record in records:
        for item in session.scalars(select(ImportItem).where(ImportItem.import_id == record.id)
                                    .order_by(ImportItem.item_index)):
            task = session.get(Task, item.task_id) if item.task_id else None
            rows.append({"record": record, "item": item, "task": task,
                         "sync_status": "duplicate" if item.status == "duplicate" else
                         task_sync_status(session, task.id) if task else "local only"})
    return rows


def history_detail(session: Session, record: ImportRecord) -> list[dict]:
    rows = []
    for item in session.scalars(select(ImportItem).where(ImportItem.import_id == record.id)
                                .order_by(ImportItem.item_index)):
        task = session.get(Task, item.task_id) if item.task_id else None
        note = session.scalar(select(Note).where(Note.task_id == task.id)) if task else None
        review = session.scalar(select(Review).where(Review.task_id == task.id)) if task else None
        node = session.get(KnowledgeNode, task.knowledge_node_id) if task else None
        operations = sorted(item_operations(session, task.id), key=lambda op: op.id) if task else []
        operation_ids = [op.id for op in operations]
        logs = list(session.scalars(select(SyncLog).where(SyncLog.operation_id.in_(operation_ids))
                                    .order_by(SyncLog.created_at.desc()).limit(30))) if operation_ids else []
        rows.append({"item": item, "task": task, "note": note, "review": review, "node": node,
                     "operations": operations, "logs": logs,
                     "sync_status": "duplicate" if item.status == "duplicate" else
                     task_sync_status(session, task.id) if task else "local only"})
    return rows


def knowledge_nodes(session: Session) -> list[KnowledgeNode]:
    return list(session.scalars(select(KnowledgeNode).order_by(KnowledgeNode.id)))


def knowledge_tree_data(session: Session) -> list[dict]:
    nodes = knowledge_nodes(session)
    tasks = Counter(session.scalars(select(Task.knowledge_node_id)))
    notes = Counter(session.scalars(select(Note.knowledge_node_id)))
    by_id = {node.id: {"node": node, "children": [], "task_count": tasks[node.id],
                       "note_count": notes[node.id]} for node in nodes}
    roots = []
    for node in nodes:
        row = by_id[node.id]
        parent = by_id.get(node.parent_id)
        (parent["children"] if parent else roots).append(row)
    def sort_branch(branch):
        branch.sort(key=lambda row: (row["node"].normalized_name.casefold(), row["node"].id))
        for row in branch:
            sort_branch(row["children"])
    sort_branch(roots)
    return roots


def prompt_tree_text(tree: list[dict]) -> str:
    lines = []
    def visit(rows, prefix="", root=False):
        for index, row in enumerate(rows):
            last = index == len(rows) - 1
            lines.append(("" if root else prefix + ("└── " if last else "├── ")) + row["node"].name)
            visit(row["children"], "" if root else prefix + ("    " if last else "│   "), False)
    visit(tree, root=True)
    return "\n".join(lines) if lines else "（暂无知识节点）"


def daily_prompt_context(tree_text: str) -> str:
    return ("【当前已有 Knowledge Tree】\n" + tree_text + "\n\n【规则】\n"
            "优先复用已有知识节点。\n只有没有合适节点时才创建新节点。\n"
            "knowledge_path 必须从宽到窄。\ncategory 必须等于 knowledge_path[0]。")


def note_sections(content: str) -> list[dict]:
    sections = []
    for line in (content or "").splitlines(keepends=True):
        match = re.match(r"^【([^】]+)】\s*(.*)$", line.strip())
        if match:
            sections.append({"heading": match.group(1), "text": match.group(2)})
        elif sections:
            sections[-1]["text"] += line
        else:
            sections.append({"heading": None, "text": line})
    return sections or [{"heading": None, "text": ""}]


def system_data(session: Session) -> dict:
    now = datetime.now(timezone.utc)
    counts = dict(session.execute(select(SyncOperation.status, func.count()).group_by(SyncOperation.status)).all())
    stale = session.scalar(select(func.count()).select_from(SyncOperation).where(
        SyncOperation.status == "processing", SyncOperation.lease_until < now)) or 0
    completed_recent = session.scalar(select(func.count()).select_from(SyncOperation).where(
        SyncOperation.status == "completed", SyncOperation.updated_at >= now - timedelta(days=1))) or 0
    try:
        revision = session.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none() or "unknown"
    except SQLAlchemyError:
        revision = "unknown"
    settings = get_settings()
    return {"counts": counts, "stale": stale, "completed_recent": completed_recent,
            "sqlite_path": make_url(settings.database_url).database,
            "alembic_revision": revision, "configured": bool(settings.notion_token and settings.notion_parent_page_id)}
