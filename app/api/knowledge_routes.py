from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.session import get_session
from app.models import KnowledgeNode, Note, Review, ReviewEvent, Task

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


def node_dict(node: KnowledgeNode) -> dict:
    return {"id": node.id, "parent_id": node.parent_id, "name": node.name,
            "path": node.path_json, "display_path": node.display_path, "level": node.level,
            "category": node.category, "description": node.description}


@router.get("/tree")
def tree(session: Session = Depends(get_session)):
    return [node_dict(node) for node in session.scalars(select(KnowledgeNode).order_by(KnowledgeNode.level, KnowledgeNode.id))]


@router.get("/{node_id}")
def detail(node_id: int, session: Session = Depends(get_session)):
    node = session.get(KnowledgeNode, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="knowledge node not found")
    tasks = list(session.scalars(select(Task).where(Task.knowledge_node_id == node_id)))
    notes = list(session.scalars(select(Note).where(Note.knowledge_node_id == node_id)))
    reviews = list(session.scalars(select(Review).where(Review.knowledge_node_id == node_id)))
    review_ids = [review.id for review in reviews]
    events = list(session.scalars(select(ReviewEvent).where(ReviewEvent.review_id.in_(review_ids)))) if review_ids else []
    return {"node": node_dict(node), "parent": node_dict(session.get(KnowledgeNode, node.parent_id)) if node.parent_id else None,
            "children": [node_dict(n) for n in session.scalars(select(KnowledgeNode).where(KnowledgeNode.parent_id == node_id))],
            "related_tasks": [{"id": t.id, "name": t.name, "date": t.date} for t in tasks],
            "related_notes": [{"id": n.id, "title": n.title} for n in notes],
            "review_history": [{"id": e.id, "review_id": e.review_id, "score": e.memory_score,
                                 "completed_at": e.completed_at} for e in events],
            "learning_count": len(tasks), "recent_learning_date": max((t.date for t in tasks), default=None),
            "next_review_date": min((r.next_review_date for r in reviews if r.status == "Scheduled"), default=None)}
