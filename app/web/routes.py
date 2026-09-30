"""Server-rendered daily-use pages and read-only prompt export."""
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.session import get_session
from app.models import ImportRecord, KnowledgeNode, Note, Review, ReviewEvent, Task
from app.web.view_data import (daily_prompt_context, dashboard_data, history_detail,
                               history_rows, knowledge_tree_data, mapping_for,
                               note_sections, notion_page_url, prompt_tree_text,
                               review_groups, system_data, task_view, today_date)

router = APIRouter(include_in_schema=False)
prompt_api = APIRouter(tags=["knowledge"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))


def page(request: Request, template: str, *, status_code: int = 200, **context):
    return templates.TemplateResponse(request=request, name=template,
                                      context={"active": context.pop("active", ""), **context},
                                      status_code=status_code)


def missing(request: Request, label: str):
    return page(request, "error.html", status_code=404, title="Page not found",
                message=f"{label} 不存在，可能已被删除。")


@router.get("/")
def dashboard(request: Request, session: Session = Depends(get_session)):
    return page(request, "dashboard.html", active="dashboard", **dashboard_data(session))


@router.get("/import")
def import_page(request: Request):
    return page(request, "import.html", active="import")


@router.get("/history")
def history_page(request: Request, session: Session = Depends(get_session)):
    return page(request, "history.html", active="history", rows=history_rows(session))


@router.get("/history/{import_id}")
def history_detail_page(import_id: int, request: Request, session: Session = Depends(get_session)):
    record = session.get(ImportRecord, import_id)
    if record is None:
        return missing(request, "导入记录")
    return page(request, "history_detail.html", active="history", record=record,
                rows=history_detail(session, record))


@router.get("/knowledge")
def knowledge_page(request: Request, session: Session = Depends(get_session)):
    return page(request, "knowledge_tree.html", active="knowledge", tree=knowledge_tree_data(session))


@router.get("/knowledge/{node_id}/view")
def knowledge_detail_page(node_id: int, request: Request, session: Session = Depends(get_session)):
    node = session.get(KnowledgeNode, node_id)
    if node is None:
        return missing(request, "知识节点")
    parent = session.get(KnowledgeNode, node.parent_id) if node.parent_id else None
    children = list(session.scalars(select(KnowledgeNode).where(KnowledgeNode.parent_id == node_id)
                                    .order_by(KnowledgeNode.normalized_name, KnowledgeNode.id)))
    tasks = list(session.scalars(select(Task).where(Task.knowledge_node_id == node_id)
                                 .order_by(Task.date.desc(), Task.id.desc())))
    notes = list(session.scalars(select(Note).where(Note.knowledge_node_id == node_id)
                                 .order_by(Note.date.desc(), Note.id.desc())))
    reviews = list(session.scalars(select(Review).where(Review.knowledge_node_id == node_id)
                                   .order_by(Review.next_review_date, Review.id)))
    events = list(session.scalars(select(ReviewEvent).where(ReviewEvent.review_id.in_([r.id for r in reviews]))
                                  .order_by(ReviewEvent.completed_at.desc()).limit(20))) if reviews else []
    mapping = mapping_for(session, "knowledge", node.id)
    return page(request, "knowledge_detail.html", active="knowledge", node=node, parent=parent,
                children=children, tasks=tasks, notes=notes, reviews=reviews, events=events,
                mapping=mapping, notion_url=notion_page_url(mapping.notion_page_id) if mapping else None)


@router.get("/tasks/{task_id}/view")
def task_detail_page(task_id: int, request: Request, session: Session = Depends(get_session)):
    task = session.get(Task, task_id)
    if task is None:
        return missing(request, "任务")
    return page(request, "task_detail.html", active="dashboard", **task_view(session, task))


@router.get("/notes/{note_id}/view")
def note_detail_page(note_id: int, request: Request, session: Session = Depends(get_session)):
    note = session.get(Note, note_id)
    if note is None:
        return missing(request, "笔记")
    task = session.get(Task, note.task_id)
    node = session.get(KnowledgeNode, note.knowledge_node_id)
    mapping = mapping_for(session, "note", note.id)
    fields = [(key, label, note.content_json.get(key, "")) for key, label in (
        ("summary", "Summary"), ("key_concepts", "Key Concepts"),
        ("detailed_explanation", "Detailed Explanation"), ("examples", "Examples"),
        ("practice", "Practice"), ("my_understanding", "My Understanding"),
        ("questions", "Questions"), ("common_mistakes", "Common Mistakes"),
        ("next_topics", "Next Topics"), ("resources", "Resources"))]
    return page(request, "note_detail.html", active="dashboard", note=note, task=task,
                node=node, fields=fields, note_sections=note_sections,
                mapping=mapping, notion_url=notion_page_url(mapping.notion_page_id) if mapping else None)


@router.get("/reviews")
def reviews_page(request: Request, session: Session = Depends(get_session)):
    return page(request, "reviews.html", active="reviews", groups=review_groups(session), day=today_date())


@router.get("/system")
def system_page(request: Request, session: Session = Depends(get_session)):
    return page(request, "system.html", active="system", **system_data(session))


@router.get("/prompt")
def prompt_page(request: Request, session: Session = Depends(get_session)):
    tree_text = prompt_tree_text(knowledge_tree_data(session))
    return page(request, "prompt_helper.html", active="prompt", tree_text=tree_text,
                daily_context=daily_prompt_context(tree_text))


@prompt_api.get("/api/knowledge/prompt-context")
def prompt_context(session: Session = Depends(get_session)):
    return {"tree_text": prompt_tree_text(knowledge_tree_data(session))}
